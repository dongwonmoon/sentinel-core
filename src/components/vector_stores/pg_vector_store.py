# -*- coding: utf-8 -*-
"""
PostgreSQL과 `pgvector` 확장을 사용하는 벡터 저장소의 구체적인 구현체입니다.
"""

import json
from typing import List, Dict, Any, Optional

from sqlalchemy import text

from ...core.database import AsyncSessionLocal
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
        self.AsyncSessionLocal = AsyncSessionLocal
        logger.info("PgVectorStore 초기화 완료.")

    @property
    def provider(self) -> str:
        """벡터 저장소 제공자 이름("pg_vector")을 반환합니다."""
        return self._provider

    async def search(
        self,
        query: str,
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
        query_embedding = self.embedding_model.embed_query(query)
        query_vec_str = str(query_embedding)
        logger.debug(f"벡터 검색 시작. k={k}, 문서 필터: {doc_ids_filter}")

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
                """
        params = {
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
        query: str,
        session_id: str,
        k: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        (거버넌스 - 듀얼 RAG)
        '임시' 세션 첨부파일 청크(`session_attachment_chunks`)를 검색합니다.

        보안: 오직 `session_id`가 일치하는 청크만 검색합니다.
        """
        query_embedding = self.embedding_model.embed_query(query)
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
