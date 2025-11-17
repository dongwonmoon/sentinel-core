# -*- coding: utf-8 -*-
"""
PostgreSQL과 `pgvector` 확장을 사용하는 벡터 저장소의 구체적인 구현체입니다.
"""

import json
from typing import List, Dict, Any, Optional

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
    PostgreSQL + pgvector를 사용하는 벡터 저장소 구현체입니다.
    `BaseVectorStore` 추상 클래스를 상속받아, 실제 데이터베이스 연동 로직을 구현합니다.
    """

    def __init__(self, settings: Settings, embedding_model: BaseEmbeddingModel):
        """
        PgVectorStore 클래스의 인스턴스를 초기화합니다.
        비동기 DB 엔진과 세션, 그리고 임베딩 모델을 설정합니다.

        Args:
            settings (Settings): 데이터베이스 연결 URL 등 애플리케이션 설정을 담은 객체.
            embedding_model (BaseEmbeddingModel): 텍스트를 벡터로 변환하는 데 사용할 임베딩 모델 객체.
        """
        self._provider = "pg_vector"
        self.embedding_model = embedding_model

        logger.info("PgVectorStore 초기화를 시작합니다...")
        try:
            # SQLAlchemy를 사용하여 비동기 데이터베이스 엔진을 생성합니다.
            # 이 엔진은 커넥션 풀을 관리하며, DB와 비동기적으로 통신합니다.
            # pool_pre_ping=True: 커넥션 풀에서 연결을 가져올 때마다 간단한 쿼리를 보내
            # 해당 연결이 유효한지 확인합니다. 이는 DB 연결이 끊어진 경우(예: 네트워크 문제, DB 재시작)
            # 발생할 수 있는 오류를 사전에 방지하여 안정성을 높입니다.
            self.engine = create_async_engine(
                settings.DATABASE_URL, pool_pre_ping=True
            )

            # 비동기 세션을 생성하기 위한 세션 팩토리(Session Factory)를 설정합니다.
            # `get_db_session` 의존성이나 백그라운드 작업에서 이 팩토리를 사용하여
            # 독립적인 DB 세션을 생성하게 됩니다.
            self.AsyncSessionLocal = sessionmaker(
                bind=self.engine, class_=AsyncSession, expire_on_commit=False
            )
            logger.info(
                "PgVectorStore 초기화 완료. 비동기 엔진 및 세션 팩토리가 설정되었습니다."
            )
        except Exception as e:
            logger.error(
                f"PgVectorStore 초기화 중 데이터베이스 엔진 생성 실패: {e}",
                exc_info=True,
            )
            raise

    @property
    def provider(self) -> str:
        """벡터 저장소 제공자 이름("pg_vector")을 반환합니다."""
        return self._provider

    async def upsert_documents(
        self, documents_data: List[Dict[str, Any]]
    ) -> None:
        """
        문서와 그 청크들을 데이터베이스에 비동기적으로 추가하거나 업데이트(Upsert)합니다.

        이 메서드는 단일 트랜잭션 내에서 다음 작업들을 수행합니다:
        1. `documents` 테이블에 문서 정보를 Upsert (INSERT or UPDATE) 합니다.
        2. `document_chunks` 테이블에서 해당 문서의 기존 청크들을 모두 삭제합니다.
        3. 새로운 청크 정보들을 `document_chunks` 테이블에 삽입합니다.

        Args:
            documents_data (List[Dict[str, Any]]): 업로드할 문서 및 청크 데이터 리스트.
        """
        if not documents_data:
            logger.warning("Upsert할 문서 데이터가 없습니다.")
            return

        doc_ids = list(set(d["doc_id"] for d in documents_data))
        logger.info(
            f"{len(doc_ids)}개 문서에 대한 {len(documents_data)}개 청크의 Upsert 작업을 시작합니다."
        )

        async with self.AsyncSessionLocal() as session:
            async with session.begin():  # 트랜잭션 시작
                try:
                    # 1. `documents` 테이블에 문서 정보 Upsert
                    # doc_id를 기준으로 중복을 확인하고, 존재하면 업데이트, 없으면 삽입합니다.
                    doc_infos = {
                        d["doc_id"]: {
                            "doc_id": d["doc_id"],
                            "source_type": d.get("source_type"),
                            "permission_groups": d.get("permission_groups", []),
                            "metadata": json.dumps(d.get("metadata", {})),
                            "owner_user_id": d.get("owner_user_id"),
                        }
                        for d in documents_data
                    }

                    # PostgreSQL의 'INSERT ... ON CONFLICT ... DO UPDATE' 구문을 사용하여
                    # 원자적인(atomic) Upsert 연산을 수행합니다. 이는 경쟁 조건(race condition)을 방지합니다.
                    # EXCLUDED는 INSERT 하려던 새로운 행의 값을 참조합니다.
                    stmt_docs_upsert = text(
                        """
                        INSERT INTO documents (doc_id, source_type, permission_groups, metadata, owner_user_id)
                        VALUES (:doc_id, :source_type, :permission_groups, :metadata, :owner_user_id)
                        ON CONFLICT (doc_id) DO UPDATE SET
                            source_type = EXCLUDED.source_type,
                            permission_groups = EXCLUDED.permission_groups,
                            metadata = EXCLUDED.metadata,
                            owner_user_id = EXCLUDED.owner_user_id,
                            last_verified_at = CURRENT_TIMESTAMP
                    """
                    )
                    await session.execute(
                        stmt_docs_upsert, list(doc_infos.values())
                    )
                    logger.debug(
                        f"{len(doc_infos)}개의 레코드를 `documents` 테이블에 Upsert했습니다."
                    )

                    # 2. `document_chunks` 테이블에서 기존 청크 삭제
                    # 새로운 청크를 삽입하기 전에, 이전 버전의 청크들을 모두 삭제하여 데이터 정합성을 유지합니다.
                    stmt_chunks_delete = text(
                        "DELETE FROM document_chunks WHERE doc_id = ANY(:doc_ids)"
                    )
                    await session.execute(
                        stmt_chunks_delete, {"doc_ids": doc_ids}
                    )
                    logger.debug(
                        f"문서 ID {doc_ids}에 해당하는 기존 청크들을 삭제했습니다."
                    )

                    # 3. 새로운 청크 정보 삽입
                    chunk_data_list = [
                        {
                            "doc_id": d["doc_id"],
                            "chunk_text": d["chunk_text"],
                            "embedding": str(
                                d["embedding"]
                            ),  # pgvector는 벡터를 문자열 형태로 받습니다.
                            "metadata": json.dumps(d.get("metadata", {})),
                        }
                        for d in documents_data
                    ]

                    stmt_chunks_insert = text(
                        """
                        INSERT INTO document_chunks (doc_id, chunk_text, embedding, metadata)
                        VALUES (:doc_id, :chunk_text, :embedding, :metadata)
                    """
                    )
                    await session.execute(stmt_chunks_insert, chunk_data_list)
                    logger.debug(
                        f"{len(chunk_data_list)}개의 새로운 청크를 `document_chunks` 테이블에 삽입했습니다."
                    )

                    logger.info(
                        f"문서 ID {doc_ids}에 대한 Upsert 트랜잭션이 성공적으로 완료되었습니다."
                    )

                except Exception as e:
                    logger.error(
                        f"PgVectorStore Upsert 중 오류 발생! 트랜잭션이 롤백됩니다. 오류: {e}",
                        exc_info=True,
                    )
                    # `async with session.begin():` 블록 내에서 예외가 발생하면,
                    # 컨텍스트 관리자가 자동으로 트랜잭션을 롤백합니다.
                    raise

    async def search(
        self,
        query_embedding: List[float],
        allowed_groups: List[str],
        k: int = 4,
        doc_ids_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        주어진 쿼리 임베딩과 유사한 문서를 비동기적으로 검색합니다.
        사용자 권한 그룹을 확인하여 접근 가능한 문서만 반환합니다.

        Args:
            query_embedding (List[float]): 검색할 쿼리의 임베딩 벡터.
            allowed_groups (List[str]): 사용자가 속한 권한 그룹 리스트.
            k (int): 반환할 최대 문서 수.
            doc_ids_filter (Optional[List[str]]): 검색 범위를 특정 문서 ID로 제한.

        Returns:
            List[Dict[str, Any]]: 검색된 문서 청크 정보의 리스트.
        """
        # asyncpg는 배열 타입에 대한 prepared statement를 덜 최적화하므로,
        # 벡터를 문자열로 캐스팅하여 SQL 쿼리에 직접 주입합니다.
        query_vec_str = str(query_embedding)
        logger.debug(
            f"벡터 검색 시작. k={k}, 허용 그룹: {allowed_groups}, 문서 필터: {doc_ids_filter}"
        )

        # CTE(Common Table Expression)를 사용하여 쿼리를 구성합니다.
        # 1. `documents`와 `document_chunks` 테이블을 조인합니다.
        # 2. `&&` 연산자(배열 교차)를 사용하여 사용자의 `allowed_groups`와 문서의 `permission_groups`가 하나라도 겹치는지 확인합니다.
        # 3. `doc_ids_filter`가 있으면 해당 문서들로 범위를 좁힙니다.
        # 4. pgvector의 `<->` 연산자(코사인 거리)를 사용하여 쿼리 임베딩과 각 청크 임베딩 사이의 거리를 계산하고 정렬합니다.
        sql_query = """
            WITH relevant_chunks AS (
                SELECT 
                    c.chunk_id,
                    c.chunk_text, 
                    c.metadata,
                    c.embedding <-> :query_embedding AS distance
                FROM 
                    document_chunks AS c
                JOIN 
                    documents AS d ON c.doc_id = d.doc_id
                WHERE
                    d.permission_groups && :allowed_groups
        """
        params = {
            "allowed_groups": allowed_groups,
            "query_embedding": query_vec_str,
            "top_k": k,
        }

        # 선택적 필터링 조건 추가
        if doc_ids_filter:
            sql_query += " AND d.doc_id = ANY(:doc_ids_filter)"
            params["doc_ids_filter"] = doc_ids_filter

        sql_query += " ORDER BY distance LIMIT :top_k) "
        sql_query += "SELECT * FROM relevant_chunks;"

        async with self.AsyncSessionLocal() as session:
            result = await session.execute(text(sql_query), params)
            search_results = [
                {
                    "chunk_text": row.chunk_text,
                    "metadata": (
                        json.loads(row.metadata)
                        if isinstance(row.metadata, str)
                        else row.metadata
                    ),
                    "score": 1
                    - row.distance,  # 코사인 거리를 유사도 점수(0~1)로 변환합니다. (0: 다름, 1: 같음)
                }
                for row in result
            ]

        logger.info(
            f"벡터 검색 완료. {len(search_results)}개의 결과를 찾았습니다."
        )
        return search_results

    async def search_session_attachments(
        self,
        query_embedding: List[float],
        session_id: str,
        k: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        (거버넌스 - 듀얼 RAG)
        '임시' 세션 첨부파일 청크(`session_attachment_chunks`)를 검색합니다.

        보안: 오직 `session_id`가 일치하는 청크만 검색합니다.
        """
        query_vec_str = str(query_embedding)
        logger.debug(
            f"세션 첨부파일(임시) 벡터 검색 시작. k={k}, session_id: {session_id}"
        )

        # `session_attachment_chunks`와 `session_attachments` 테이블을 조인하여
        # 주어진 `session_id`에 속하고, 상태가 'temporary'(인덱싱 완료)인 청크만 검색 대상으로 합니다.
        sql_query = """
            SELECT 
                c.chunk_id,
                c.chunk_text, 
                c.extra_metadata AS metadata,
                c.embedding <-> :query_embedding AS distance
            FROM 
                session_attachment_chunks AS c
            JOIN 
                session_attachments AS a ON c.attachment_id = a.attachment_id
            WHERE
                a.session_id = :session_id
                AND a.status = 'temporary' -- 인덱싱이 완료된 파일만
            ORDER BY
                distance
            LIMIT :top_k
        """
        params = {
            "query_embedding": query_vec_str,
            "session_id": session_id,
            "top_k": k,
        }

        async with self.AsyncSessionLocal() as session:
            result = await session.execute(text(sql_query), params)
            search_results = [
                {
                    "chunk_text": row.chunk_text,
                    "metadata": (
                        json.loads(row.metadata)
                        if isinstance(row.metadata, str)
                        else row.metadata
                    ),
                    "score": 1 - row.distance,  # 거리를 유사도 점수(0~1)로 변환
                }
                for row in result
            ]

        logger.info(
            f"세션 첨부파일 벡터 검색 완료. {len(search_results)}개의 결과를 찾았습니다."
        )
        return search_results

    async def delete_documents(self, doc_ids: List[str]) -> int:
        """
        주어진 문서 ID 목록과 일치하는 모든 문서를 삭제합니다.

        삭제는 `documents` 테이블에서 시작되며, `document_chunks` 테이블의
        관련 청크는 데이터베이스의 `ON DELETE CASCADE` 외래 키 제약 조건에 의해 자동으로 삭제됩니다.

        Args:
            doc_ids (List[str]): 삭제할 문서의 고유 ID 리스트.

        Returns:
            int: 성공적으로 삭제된 `documents` 레코드의 수.
        """
        if not doc_ids:
            logger.warning("삭제할 문서 ID가 제공되지 않았습니다.")
            return 0

        logger.info(f"문서 ID {doc_ids}에 대한 삭제 작업을 시작합니다.")

        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                # `ANY` 연산자를 사용하여 여러 문서 ID를 한 번의 쿼리로 효율적으로 처리합니다.
                stmt = text(
                    "DELETE FROM documents WHERE doc_id = ANY(:doc_ids)"
                )
                result = await session.execute(stmt, {"doc_ids": doc_ids})
                # `rowcount`는 이 실행으로 인해 영향을 받은(삭제된) 행의 수를 반환합니다.
                deleted_count = result.rowcount

        logger.info(
            f"총 {deleted_count}개의 문서 레코드와 관련 청크들이 삭제되었습니다."
        )
        return deleted_count
