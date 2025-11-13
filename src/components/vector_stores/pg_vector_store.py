import json
from typing import List, Tuple, Optional

from langchain_core.documents import Document
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from ...core.config import Settings
from ..embeddings.base import BaseEmbeddingModel
from .base import BaseVectorStore
from ...core.logger import get_logger

logger = get_logger(__name__)


class PgVectorStore(BaseVectorStore):
    """
    PostgreSQL + pgvector를 사용하는 벡터 스토어 구현체입니다.
    BaseVectorStore 추상 클래스를 상속받습니다.
    """

    def __init__(self, settings: Settings, embedding_model: BaseEmbeddingModel):
        """
        PgVectorStore 클래스의 인스턴스를 초기화합니다.
        비동기 DB 엔진과 세션, 그리고 임베딩 모델을 설정합니다.

        Args:
            settings: 애플리케이션의 설정을 담고 있는 Settings 객체입니다.
            embedding_model: 텍스트를 벡터로 변환하는 데 사용할 임베딩 모델 객체입니다.
        """
        # 비동기 데이터베이스 엔진을 생성합니다.
        self.engine = create_async_engine(settings.DATABASE_URL)
        # 비동기 세션을 생성하기 위한 세션 팩토리를 설정합니다.
        self.AsyncSessionLocal = sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )
        # 텍스트 임베딩을 위한 모델을 설정합니다.
        self.embedding_model = embedding_model
        logger.info(
            "PgVectorStore 초기화 완료. 비동기 엔진 및 임베딩 모델이 설정되었습니다."
        )

    async def upsert_documents(
        self,
        documents: List[Document],
        permission_groups: List[str],
    ) -> None:
        """
        문서를 벡터 스토어에 비동기적으로 추가하거나 업데이트(upsert)합니다.
        문서 ID를 기준으로 기존 청크를 삭제한 후 새로 추가하는 방식을 사용합니다.

        Args:
            documents: LangChain의 Document 객체 리스트입니다. 각 Document는 content와 metadata를 가집니다.
            permission_groups: 이 문서들에 접근할 수 있는 권한 그룹의 리스트입니다.
        """
        if not documents:
            return

        # 문서 내용(page_content)을 임베딩합니다.
        embeddings = self.embedding_model.embed_documents(
            [doc.page_content for doc in documents]
        )
        doc_ids_to_clear = list(
            set(doc.metadata.get("doc_id") for doc in documents)
        )

        async with self.AsyncSessionLocal() as session:
            async with session.begin():  # 트랜잭션 시작
                try:
                    # 1. 기존 문서 및 청크 정보 업데이트/삭제
                    # documents 테이블에 UPSERT
                    doc_infos = {}
                    for doc in documents:
                        doc_id = doc.metadata.get("doc_id")
                        if doc_id not in doc_infos:
                            doc_infos[doc_id] = {
                                "doc_id": doc_id,
                                "source_type": doc.metadata.get("source_type"),
                                "permission_groups": permission_groups,
                                "metadata": json.dumps(doc.metadata),
                            }

                    if doc_infos:
                        stmt_docs_upsert = text(
                            """
                            INSERT INTO documents (doc_id, source_type, permission_groups, metadata)
                            VALUES (:doc_id, :source_type, :permission_groups, :metadata) 
                            ON CONFLICT (doc_id) DO UPDATE SET
                                source_type = EXCLUDED.source_type,
                                permission_groups = EXCLUDED.permission_groups,
                                metadata = EXCLUDED.metadata
                        """
                        )
                        await session.execute(
                            stmt_docs_upsert, list(doc_infos.values())
                        )

                    # document_chunks 테이블에서 기존 청크 삭제
                    if doc_ids_to_clear:
                        await session.execute(
                            text(
                                "DELETE FROM document_chunks WHERE doc_id = ANY(:doc_ids)"
                            ),
                            {"doc_ids": doc_ids_to_clear},
                        )

                    # 2. 새로운 청크 정보 추가
                    chunk_data_list = []
                    for i, doc in enumerate(documents):
                        chunk_data_list.append(
                            {
                                "doc_id": doc.metadata.get("doc_id"),
                                "chunk_text": doc.page_content,
                                "embedding": str(embeddings[i]),
                                "metadata": json.dumps(doc.metadata),
                            }
                        )

                    if chunk_data_list:
                        stmt_chunks_insert = text(
                            """
                            INSERT INTO document_chunks (doc_id, chunk_text, embedding, metadata)
                            VALUES (:doc_id, :chunk_text, :embedding, :metadata)
                        """
                        )
                        await session.execute(
                            stmt_chunks_insert, chunk_data_list
                        )

                    logger.info(
                        f"{len(doc_infos)}개 문서, {len(documents)}개 청크 Upsert 완료."
                    )

                except Exception as e:
                    logger.error(
                        f"PgVectorStore Upsert 중 에러 발생! 롤백됩니다. {e}",
                        exc_info=True,
                    )
                    raise

    async def search(
        self,
        query: str,
        allowed_groups: List[str],
        k: int = 4,
        doc_ids_filter: Optional[List[str]] = None,
    ) -> List[Tuple[Document, float]]:
        """
        주어진 쿼리와 유사한 문서를 비동기적으로 검색합니다.
        사용자 권한 그룹을 확인하여 접근 가능한 문서만 반환합니다.

        Args:
            query: 검색할 쿼리 텍스트입니다.
            allowed_groups: 사용자가 속한 권한 그룹의 리스트입니다.
            k: 반환할 최대 문서 수입니다.

        Returns:
            (Document, 유사도 점수) 튜플의 리스트를 반환합니다.
        """
        # 쿼리를 임베딩 벡터로 변환합니다.
        query_embedding = self.embedding_model.embed_query(query)
        query_vec_str = str(query_embedding)

        # SQL 쿼리문. f-string을 사용하지만, SQL Injection에 안전하게 처리합니다.
        # 벡터 검색 부분은 f-string으로, 나머지 파라미터는 바인딩으로 처리합니다.
        sql_query = f"""
            SELECT 
                c.chunk_text, 
                c.metadata,
                c.embedding <-> '{query_vec_str}'::vector AS distance
            FROM 
                document_chunks AS c
            JOIN 
                documents AS d ON c.doc_id = d.doc_id
            WHERE
                d.permission_groups && :allowed_groups
        """

        params = {"allowed_groups": allowed_groups, "top_k": k}

        if doc_ids_filter:
            where_clauses = []
            for i, f in enumerate(doc_ids_filter):
                if f.endswith("/"):
                    # 'file-upload-my_repo.zip/' 같은 접두사(Prefix)인 경우
                    param_name = f"p{i}"
                    where_clauses.append(f"d.doc_id LIKE :{param_name}")
                    params[param_name] = f + "%"  # 와일드카드 추가
                else:
                    # 'file-upload-hr_policy.txt' 같은 정확한 ID인 경우
                    param_name = f"id{i}"
                    where_clauses.append(f"d.doc_id = :{param_name}")
                    params[param_name] = f

            if where_clauses:
                sql_query += " AND (" + " OR ".join(where_clauses) + ")"
                logger.info(f"컨텍스트 필터 적용: {where_clauses}")

        sql_query += " ORDER BY distance LIMIT :top_k"

        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                text(sql_query),
                params,
            )

            search_results = []
            for row in result:
                # DB에서 읽어온 메타데이터(JSON 문자열)를 파싱합니다.
                metadata = (
                    json.loads(row.metadata)
                    if isinstance(row.metadata, str)
                    else row.metadata
                )

                # LangChain Document 객체로 변환합니다.
                doc = Document(page_content=row.chunk_text, metadata=metadata)
                search_results.append((doc, row.distance))

            logger.info(
                f"'{query[:20]}...' 쿼리로 {len(search_results)}개 결과 검색 완료."
            )
            return search_results

    async def delete_documents(
        self, doc_id_or_prefix: str, permission_groups: List[str]
    ) -> int:
        """
        주어진 doc_id (정확히 일치) 또는 doc_id 접두사(prefix, e.g., 'github-repo-name/')와
        일치하는 모든 문서를 삭제합니다.

        삭제는 'documents' 테이블에서 시작되며, 'document_chunks' 테이블의
        관련 청크는 'ON DELETE CASCADE' 외래 키 제약 조건에 의해 자동으로 삭제됩니다.
        (참고: alembic/versions/711d0b8478e2...py 에서 ondelete='CASCADE' 설정 확인)

        Returns:
            삭제된 문서(documents) 레코드의 수.
        """
        logger.info(
            f"'{doc_id_or_prefix}' 문서 삭제 시도 (Groups: {permission_groups})..."
        )

        # PgVectorStore가 직접 DB 세션을 관리하도록
        async with self.AsyncSessionLocal() as session:
            async with session.begin():  # 트랜잭션 시작

                # 접두사(Prefix)인지, 정확한 ID인지 확인
                if doc_id_or_prefix.endswith("/"):
                    # 'github-repo-name/' 또는 'file-upload-zip-name/'
                    stmt = text(
                        """
                        DELETE FROM documents
                        WHERE doc_id LIKE :prefix
                          AND permission_groups && :allowed_groups
                    """
                    )
                    params = {
                        "prefix": doc_id_or_prefix + "%",  # 와일드카드 추가
                        "allowed_groups": permission_groups,
                    }
                else:
                    # 'file-upload-hr_policy.txt'
                    stmt = text(
                        """
                        DELETE FROM documents
                        WHERE doc_id = :doc_id
                          AND permission_groups && :allowed_groups
                    """
                    )
                    params = {
                        "doc_id": doc_id_or_prefix,
                        "allowed_groups": permission_groups,
                    }

                result = await session.execute(stmt, params)
                deleted_count = result.rowcount  # 영향을 받은(삭제된) 행의 수

        logger.info(f"총 {deleted_count}개의 문서 레코드 삭제 완료.")
        return deleted_count
