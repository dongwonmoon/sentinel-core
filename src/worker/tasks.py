# -*- coding: utf-8 -*-
"""
Celery 워커가 실제로 수행할 비동기 작업(Task)들을 정의합니다.

이 모듈의 함수들은 `@celery_app.task` 데코레이터를 통해 Celery 태스크로 등록됩니다.
API 서버의 응답 시간을 저하시키지 않으면서 시간이 오래 걸리는 작업들을
백그라운드에서 비동기적으로 처리하는 것이 주 목적입니다.

주요 태스크 종류:
- **문서 인덱싱**: 파일, ZIP 압축 파일, GitHub 리포지토리 등 다양한 소스로부터 문서를 읽어와
  청크로 분할하고, 임베딩을 생성하여 벡터 DB에 저장합니다.
- **임시 파일 처리**: 사용자가 채팅 세션에 임시로 첨부한 파일을 인덱싱하여 '듀얼 RAG'에 사용될
  'Session KB'를 구축합니다.
- **스케줄링된 작업 (Beat)**: 주기적으로 실행되어야 하는 작업들을 정의합니다. (예: 오래된 문서 검사,
  사용자 정의 스케줄 작업 실행)
- **거버넌스 및 알림**: 관리자 승인에 따라 임시 지식을 영구 지식으로 승격시키거나, 특정 사용자/그룹에게
  알림을 보냅니다.
"""

import asyncio
import io
import json
import os
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List

from croniter import croniter
from git import Repo
from git.exc import GitCommandError
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from ..components.llms.base import BaseLLM
from ..core import factories, prompts
from ..core.config import get_settings
from ..core.logger import get_logger
from ..db import models as db_models
from .celery_app import celery_app

logger = get_logger(__name__)

# --- 헬퍼 함수 및 상수 ---

# 파일 확장자와 LangChain의 코드 분할기 언어 타입 매핑
CODE_LANGUAGE_MAP = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".ts": Language.TS,
    ".java": Language.JAVA,
    ".go": Language.GO,
    ".c": Language.C,
    ".cpp": Language.CPP,
    ".h": Language.C,
    ".md": Language.MARKDOWN,
}


@contextmanager
def get_sync_db_session():
    """
    Celery 태스크와 같이 동기적인 컨텍스트에서 SQLAlchemy 동기(Synchronous) DB 세션을
    안전하게 생성하고 사용하기 위한 컨텍스트 관리자입니다.
    작업 완료 시 자동으로 commit하며, 오류 발생 시 rollback 후 세션을 닫습니다.
    """
    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"동기 DB 세션 중 오류 발생! 롤백됩니다. {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


async def _generate_hypothetical_question(chunk_text: str, llm: BaseLLM) -> str:
    """
    [비동기 헬퍼] LLM을 호출하여 청크 내용에 기반한 가상 질문(Hypothetical Question)을 생성합니다.
    이는 HyDE(Hypothetical Document Embeddings) 기법의 일부로, 원본 청크 대신 이 질문을
    임베딩하여 검색 정확도를 높이는 것을 목표로 합니다.
    """
    if not chunk_text.strip():
        return ""
    prompt = prompts.HYPOTHETICAL_QUESTION_PROMPT.format(chunk_text=chunk_text)
    try:
        # LLM 호출이 무한정 길어지는 것을 방지하기 위해 타임아웃 설정
        response = await asyncio.wait_for(
            llm.invoke([HumanMessage(content=prompt)], config={}), timeout=15.0
        )
        question = response.content.strip()
        logger.debug(f"HyDE 생성: 원본 '%.20s...' -> 질문 '%s'", chunk_text, question)
        return question
    except asyncio.TimeoutError:
        logger.warning(f"HyDE: 가상 질문 생성 시간 초과 (원본: '%.20s...')", chunk_text)
        return chunk_text  # 실패 시 원본 텍스트를 그대로 반환하여 임베딩 소스로 사용
    except Exception as e:
        logger.warning(
            f"HyDE: 가상 질문 생성 실패 (원본: '%.20s...'): %s", chunk_text, e
        )
        return chunk_text  # 실패 시 원본 텍스트를 그대로 반환


async def _load_and_split_documents(
    temp_file_path: str,
    file_name: str,
    text_splitter_default: RecursiveCharacterTextSplitter,
    llm: BaseLLM,
) -> List[Document]:
    """
    [비동기 헬퍼] 단일 파일을 종류에 맞는 로더와 스플리터로 분할하고,
    각 청크에 대한 가상 질문(HyDE)을 병렬로 생성합니다.
    """
    file_ext = os.path.splitext(file_name)[1].lower()
    logger.debug(f"문서 로드 및 분할 시작: 파일='{file_name}', 확장자='{file_ext}'")

    # 1. 파일 확장자에 따라 적절한 로더 선택
    if file_ext == ".pdf":
        loader = PyPDFLoader(temp_file_path)
    elif file_ext == ".md":
        loader = UnstructuredMarkdownLoader(temp_file_path)
    else:  # .txt, .py, .js 등 텍스트 기반 파일
        loader = TextLoader(temp_file_path, autodetect_encoding=True)

    docs = loader.load()

    # 2. 코드 파일의 경우, 언어에 특화된 스플리터 사용
    language = CODE_LANGUAGE_MAP.get(file_ext)
    splitter = text_splitter_default
    if language and language != Language.MARKDOWN:
        try:
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=language, chunk_size=1000, chunk_overlap=200
            )
            logger.debug(f"'{language.value}' 언어용 스플리터를 사용합니다.")
        except Exception:
            logger.warning(
                f"'{language.value}'용 코드 스플리터 사용 실패. 기본 스플리터로 대체합니다."
            )

    split_chunks = splitter.split_documents(docs)
    logger.debug(f"'{file_name}' 파일을 {len(split_chunks)}개의 청크로 분할했습니다.")

    # 3. 각 청크에 대해 가상 질문을 비동기적으로 병렬 생성 (HyDE)
    tasks = [
        _generate_hypothetical_question(chunk.page_content, llm)
        for chunk in split_chunks
    ]
    hypothetical_questions = await asyncio.gather(*tasks)

    # 4. 최종적으로 반환할 문서 목록에 가상 질문을 메타데이터로 추가
    final_docs = []
    for i, chunk in enumerate(split_chunks):
        chunk.metadata["embedding_source_text"] = hypothetical_questions[i]
        final_docs.append(chunk)

    return final_docs


def _initialize_components_for_task() -> Dict[str, Any]:
    """
    Celery 태스크가 실행될 때마다 필요한 핵심 컴포넌트들을 초기화하고 반환합니다.
    Celery 워커는 별도의 프로세스에서 실행되므로, API 서버와 메모리를 공유하지 않기 때문에
    각 태스크 실행 시 필요한 객체들을 독립적으로 생성해야 합니다.
    """
    logger.debug("Celery 태스크를 위한 컴포넌트 초기화를 시작합니다.")
    settings = get_settings()
    embedding_model = factories.create_embedding_model(
        settings.embedding, settings, settings.OPENAI_API_KEY
    )
    vector_store = factories.create_vector_store(
        settings.vector_store, settings, embedding_model
    )
    fast_llm = factories.create_llm(
        settings.llm.fast, settings, settings.OPENAI_API_KEY
    )
    text_splitter_default = RecursiveCharacterTextSplitter(
        chunk_size=1000, chunk_overlap=200
    )
    logger.debug("Celery 태스크 컴포넌트 초기화 완료.")
    return {
        "embedding_model": embedding_model,
        "vector_store": vector_store,
        "fast_llm": fast_llm,
        "text_splitter_default": text_splitter_default,
    }


# --- Celery 태스크 정의 ---


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_session_attachment_indexing(
    self, attachment_id: int, file_path: str, file_name: str
):
    """
    [Celery Task] 사용자가 세션에 첨부한 '임시' 파일을 인덱싱하여 'Session KB'를 구축합니다.
    이 작업은 '듀얼 RAG'에서 실시간으로 참조할 수 있는 세션 한정 지식을 생성합니다.

    Args:
        self (celery.Task): `bind=True`로 인해 주입되는 태스크 인스턴스. 재시도 등에 사용됩니다.
        attachment_id (int): 처리할 파일의 DB 레코드 ID (session_attachments.attachment_id).
        file_path (str): API 서버가 저장한 임시 파일의 실제 경로.
        file_name (str): 사용자가 업로드한 원본 파일 이름.
    """
    task_id = self.request.id
    logger.info(
        f"--- [Celery Task ID: {task_id}] '임시 파일' 인덱싱 시작 (Attachment ID: {attachment_id}, 파일: {file_name}) ---"
    )

    try:
        # 1. 태스크 실행에 필요한 컴포넌트 초기화
        components = _initialize_components_for_task()
        vector_store = components["vector_store"]
        fast_llm = components["fast_llm"]
        text_splitter_default = components["text_splitter_default"]

        # 2. 파일 로드, 분할 및 HyDE 질문 생성
        # Celery 태스크는 동기 컨텍스트이므로, 비동기 헬퍼 함수를 실행하기 위해
        # `asyncio.run`을 사용해 임시 이벤트 루프에서 실행합니다.
        split_chunks = asyncio.run(
            _load_and_split_documents(
                file_path,
                file_name,
                text_splitter_default,
                fast_llm,
            )
        )

        if not split_chunks:
            logger.warning(f"'{file_name}' 처리 후 인덱싱할 청크가 없습니다.")
            # (향후 DB 상태를 'failed'로 업데이트하는 로직 추가 가능)
            return {"status": "warning", "message": "No content to index."}

        # 3. 임베딩 생성 (HyDE 질문 또는 원본 텍스트 사용)
        embedding_source_texts = [
            chunk.metadata.get("embedding_source_text", chunk.page_content)
            for chunk in split_chunks
        ]
        chunk_embeddings = vector_store.embedding_model.embed_documents(
            embedding_source_texts
        )

        # 4. 'session_attachment_chunks' 테이블에 저장할 데이터 준비
        chunks_to_store = [
            {
                "attachment_id": attachment_id,
                "chunk_text": chunk.page_content,
                "embedding": str(embedding_vector),  # pgvector는 문자열 리스트로 받음
                "extra_metadata": json.dumps(chunk.metadata),
            }
            for chunk, embedding_vector in zip(split_chunks, chunk_embeddings)
        ]

        # 5. DB에 청크 데이터 저장 및 부모 파일 상태 업데이트
        async def save_chunks_to_db():
            if not hasattr(vector_store, "AsyncSessionLocal"):
                raise TypeError("Vector store is missing AsyncSessionLocal")

            async with vector_store.AsyncSessionLocal() as session:
                async with session.begin():
                    # 5a. 청크 삽입
                    stmt_chunks_insert = text(
                        """
                        INSERT INTO session_attachment_chunks
                        (attachment_id, chunk_text, embedding, extra_metadata)
                        VALUES (:attachment_id, :chunk_text, :embedding, :extra_metadata)
                        """
                    )
                    await session.execute(stmt_chunks_insert, chunks_to_store)

                    # 5b. 부모 Attachment 상태를 'temporary'(인덱싱 완료, 사용 가능)로 업데이트
                    stmt_update_status = text(
                        """
                        UPDATE session_attachments
                        SET status = 'temporary'
                        WHERE attachment_id = :attachment_id
                        """
                    )
                    await session.execute(
                        stmt_update_status, {"attachment_id": attachment_id}
                    )

        asyncio.run(save_chunks_to_db())

        success_message = (
            f"'{file_name}' 임시 인덱싱 완료. {len(chunks_to_store)}개 청크 저장됨."
        )
        logger.info(
            f"--- [Celery Task ID: {task_id}] 임시 인덱싱 성공: {success_message} ---"
        )
        return {"status": "success", "message": success_message}

    except Exception as e:
        logger.error(
            f"--- [Celery Task ID: {task_id}] '{file_name}' 임시 인덱싱 중 심각한 오류 발생: {e} ---",
            exc_info=True,
        )
        # (향후 실패 시 DB 상태를 'failed'로 업데이트하는 로직 추가 권장)
        # `self.retry`를 호출하여 Celery에게 이 작업을 재시도하도록 요청합니다.
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_indexing(
    self,
    file_content: bytes,
    file_name: str,
    permission_groups: List[str],
    owner_user_id: int,
):
    """
    [Celery Task] 단일 파일 또는 ZIP 압축 파일을 인덱싱하여 '영구 지식 베이스(KB)'에 저장합니다.
    ZIP 파일의 경우, 내부의 모든 파일을 재귀적으로 처리합니다.
    """
    task_id = self.request.id
    logger.info(
        f"--- [Celery Task ID: {task_id}] '{file_name}' 영구 인덱싱 시작 (권한: {permission_groups}, 소유자: {owner_user_id}) ---"
    )

    try:
        components = _initialize_components_for_task()
        vector_store = components["vector_store"]
        fast_llm = components["fast_llm"]
        text_splitter_default = components["text_splitter_default"]

        all_chunks_to_index = []
        total_files_processed = 0

        # 1. ZIP 파일 처리 로직
        if file_name.lower().endswith(".zip"):
            logger.info(
                f"'{file_name}'은 ZIP 파일입니다. 압축 해제 및 내부 파일 처리를 시작합니다."
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                with io.BytesIO(file_content) as zip_buffer:
                    with zipfile.ZipFile(zip_buffer, "r") as zf:
                        zf.extractall(temp_dir)

                for root, _, files in os.walk(temp_dir):
                    # 숨김 파일 및 __pycache__ 와 같은 불필요한 디렉토리 건너뛰기
                    if (
                        any(part.startswith(".") for part in root.split(os.sep))
                        or "__pycache__" in root
                    ):
                        continue

                    for file in files:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, temp_dir)

                        try:
                            chunks = asyncio.run(
                                _load_and_split_documents(
                                    file_path,
                                    relative_path,
                                    text_splitter_default,
                                    fast_llm,
                                )
                            )
                            # doc_id를 '접두사/상대경로' 형태로 구성하여 고유성 보장
                            base_doc_id_prefix = (
                                f"file-upload-{file_name.rsplit('.zip', 1)[0]}"
                            )
                            doc_id = f"{base_doc_id_prefix}/{relative_path}"
                            for chunk in chunks:
                                chunk.metadata.update(
                                    {
                                        "doc_id": doc_id,
                                        "source_type": "file-upload-zip",
                                        "original_zip": file_name,
                                        "source": relative_path,
                                    }
                                )
                            all_chunks_to_index.extend(chunks)
                            total_files_processed += 1
                        except Exception as e:
                            logger.warning(
                                f"ZIP 내 파일 '{relative_path}' 처리 중 오류 발생: {e}"
                            )
        else:
            # 2. 단일 파일 처리
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{file_name}"
            ) as tmp_file:
                tmp_file.write(file_content)
                temp_file_path = tmp_file.name

            try:
                chunks = asyncio.run(
                    _load_and_split_documents(
                        temp_file_path,
                        file_name,
                        text_splitter_default,
                        fast_llm,
                    )
                )
                doc_id = f"file-upload-{file_name}"
                for chunk in chunks:
                    chunk.metadata.update(
                        {
                            "doc_id": doc_id,
                            "source_type": "file-upload",
                            "source": file_name,
                        }
                    )
                all_chunks_to_index.extend(chunks)
                total_files_processed = 1
            finally:
                os.remove(temp_file_path)

        if not all_chunks_to_index:
            logger.warning(
                f"'{file_name}' 처리 후 인덱싱할 청크가 없습니다. 파일이 비어있거나 지원하지 않는 형식일 수 있습니다."
            )
            return {
                "status": "warning",
                "message": "No content could be indexed from the file(s).",
            }

        # 3. 수집된 모든 청크를 벡터 저장소에 Upsert
        documents_data = [
            {
                "doc_id": chunk.metadata["doc_id"],
                "chunk_text": chunk.page_content,
                "embedding": chunk.metadata["embedding_source_text"],
                "metadata": chunk.metadata,
                "source_type": chunk.metadata["source_type"],
                "permission_groups": permission_groups,
                "owner_user_id": owner_user_id,
            }
            for chunk in all_chunks_to_index
        ]
        asyncio.run(vector_store.upsert_documents(documents_data=documents_data))

        success_message = f"'{file_name}' 처리 완료. {total_files_processed}개 파일에서 {len(all_chunks_to_index)}개 청크를 인덱싱했습니다."
        logger.info(
            f"--- [Celery Task ID: {task_id}] 인덱싱 성공: {success_message} ---"
        )
        return {"status": "success", "message": success_message}

    except Exception as e:
        logger.error(
            f"--- [Celery Task ID: {task_id}] '{file_name}' 인덱싱 중 심각한 오류 발생: {e} ---",
            exc_info=True,
        )
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def process_github_repo_indexing(
    self, repo_url: str, permission_groups: List[str], owner_user_id: int
):
    """[Celery Task] GitHub 저장소를 클론하고, 내부의 모든 텍스트 기반 파일들을 인덱싱합니다."""
    task_id = self.request.id
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    logger.info(
        f"--- [Celery Task ID: {task_id}] GitHub 리포지토리 '{repo_name}' 인덱싱 시작 ---"
    )

    try:
        components = _initialize_components_for_task()
        vector_store = components["vector_store"]
        fast_llm = components["fast_llm"]
        text_splitter_default = components["text_splitter_default"]

        all_chunks_to_index = []
        total_files_processed = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"'{repo_name}' 클론을 시작합니다. 대상 디렉토리: {temp_dir}")
            # `depth=50` 옵션으로 최근 50개 커밋만 가져와 클론 속도 및 용량 최적화
            Repo.clone_from(repo_url, temp_dir, depth=50)
            logger.info(f"'{repo_name}' 클론 완료.")

            for root, _, files in os.walk(temp_dir):
                # .git 디렉토리는 무시
                if ".git" in root.split(os.sep):
                    continue
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, temp_dir)
                    try:
                        chunks = asyncio.run(
                            _load_and_split_documents(
                                file_path,
                                relative_path,
                                text_splitter_default,
                                fast_llm,
                            )
                        )
                        doc_id = f"github-repo-{repo_name}/{relative_path}"
                        for chunk in chunks:
                            chunk.metadata.update(
                                {
                                    "doc_id": doc_id,
                                    "source_type": "github-repo",
                                    "repo_url": repo_url,
                                    "repo_name": repo_name,
                                    "source": relative_path,
                                }
                            )
                        all_chunks_to_index.extend(chunks)
                        total_files_processed += 1
                    except Exception as e:
                        logger.warning(
                            f"GitHub 리포지토리 내 파일 '{relative_path}' 처리 중 오류: {e}"
                        )

        if not all_chunks_to_index:
            logger.warning(
                f"'{repo_name}' 리포지토리에서 인덱싱할 콘텐츠를 찾지 못했습니다."
            )
            return {
                "status": "warning",
                "message": "No content could be indexed from the repository.",
            }

        documents_data = [
            {
                "doc_id": chunk.metadata["doc_id"],
                "chunk_text": chunk.page_content,
                "embedding": chunk.metadata["embedding_source_text"],
                "metadata": chunk.metadata,
                "source_type": chunk.metadata["source_type"],
                "permission_groups": permission_groups,
                "owner_user_id": owner_user_id,
            }
            for chunk in all_chunks_to_index
        ]
        asyncio.run(vector_store.upsert_documents(documents_data=documents_data))

        success_message = f"'{repo_name}' 처리 완료. {total_files_processed}개 파일에서 {len(all_chunks_to_index)}개 청크를 인덱싱했습니다."
        logger.info(
            f"--- [Celery Task ID: {task_id}] GitHub 인덱싱 성공: {success_message} ---"
        )
        return {"status": "success", "message": success_message}

    except GitCommandError as e:
        logger.error(
            f"--- [Celery Task ID: {task_id}] Git 클론 실패: {repo_url}. 오류: {e} ---",
            exc_info=True,
        )
        # Git 오류는 재시도해도 해결되지 않을 가능성이 높으므로, 재시도하지 않고 바로 실패 처리
        return {
            "status": "error",
            "message": f"Failed to clone repository: {repo_url}. Please check the URL and permissions.",
        }
    except Exception as e:
        logger.error(
            f"--- [Celery Task ID: {task_id}] '{repo_name}' 인덱싱 중 심각한 오류 발생: {e} ---",
            exc_info=True,
        )
        raise self.retry(exc=e)


# ==============================================================================
# 주기적 실행(Scheduled) 및 거버넌스 태스크
# ==============================================================================


@celery_app.task
def check_stale_documents(days_old: int = 180):
    """
    [Beat Task] 주기적으로 실행되어, 오래된(stale) 문서를 스캔하고 소유자에게 알림을 보냅니다.
    지식 베이스의 최신성을 유지하기 위한 거버넌스 기능입니다.
    """
    logger.info(
        f"[Beat Task] {days_old}일 이상 검증되지 않은 오래된 문서 스캔을 시작합니다..."
    )

    find_stale_stmt = text(
        f"""
        SELECT doc_id, owner_user_id, last_verified_at, extra_metadata
        FROM documents
        WHERE last_verified_at < NOW() - INTERVAL '{days_old} days' AND owner_user_id IS NOT NULL
    """
    )
    insert_notification_stmt = text(
        "INSERT INTO user_notifications (user_id, message) VALUES (:user_id, :message)"
    )

    notifications_sent = 0
    try:
        with get_sync_db_session() as session:
            stale_documents = session.execute(find_stale_stmt).fetchall()
            if not stale_documents:
                logger.info("[Beat Task] 오래된 문서가 없습니다. 작업을 종료합니다.")
                return "No stale documents found."

            logger.warning(
                f"[Beat Task] {len(stale_documents)}개의 오래된 문서를 발견했습니다. 알림 생성을 시작합니다."
            )
            notifications_to_create = []
            for doc in stale_documents:
                doc_dict = doc._asdict()
                doc_name = (doc_dict.get("extra_metadata", {}) or {}).get(
                    "original_zip"
                ) or doc_dict.get("doc_id")
                notifications_to_create.append(
                    {
                        "user_id": doc_dict["owner_user_id"],
                        "message": f"지식 소스 '{doc_name}'가 {days_old}일 이상 검증되지 않았습니다. 관리 페이지에서 재업데이트하거나 삭제하는 것을 고려해 보세요.",
                    }
                )

            if notifications_to_create:
                session.execute(insert_notification_stmt, notifications_to_create)
                notifications_sent = len(notifications_to_create)
    except Exception as e:
        logger.error(f"[Beat Task] 오래된 문서 스캔 중 오류 발생: {e}", exc_info=True)
        return f"Error during stale document check: {e}"

    logger.info(f"[Beat Task] 스캔 완료. {notifications_sent}개의 알림을 생성했습니다.")
    return f"Scan complete. Sent {notifications_sent} notifications."


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_scheduled_github_summary(self, task_id: int, user_id: int, repo_url: str):
    """
    [User Task] 사용자가 DB에 등록한 스케줄에 따라, 특정 GitHub 리포지토리의
    최근 24시간 커밋을 요약하고 사용자에게 알림을 보냅니다.
    """
    task_id_celery = self.request.id
    logger.info(
        f"[Sched Task / Celery ID: {task_id_celery}] DB Task {task_id} (사용자: {user_id}) '{repo_url}' 요약 시작..."
    )

    try:
        settings = get_settings()
        fast_llm = factories.create_llm(settings.llm.fast, settings)

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Repo.clone_from(repo_url, temp_dir, depth=50)
            commits = list(repo.iter_commits(since="24.hours.ago"))
            if not commits:
                logger.info(
                    f"[Sched Task] DB Task {task_id}: '{repo_url}'에 새로운 커밋이 없습니다."
                )
                return "No new commits found in the last 24 hours."
            commit_messages = "\n".join(
                [f"- {c.message.splitlines()[0]}" for c in commits]
            )

        prompt = prompts.SUMMARY_PROMPT_TEMPLATE.format(commit_messages=commit_messages)
        response = asyncio.run(
            fast_llm.invoke([HumanMessage(content=prompt)], config={})
        )
        summary = response.content.strip()

        repo_name = repo_url.split("/")[-1].replace(".git", "")
        notification_message = f"'{repo_name}' 데일리 커밋 요약:\n{summary}"

        with get_sync_db_session() as session:
            session.execute(
                text(
                    "INSERT INTO user_notifications (user_id, message) VALUES (:user_id, :message)"
                ),
                {"user_id": user_id, "message": notification_message},
            )

        logger.info(
            f"[Sched Task] DB Task {task_id}: '{repo_name}' 요약 및 알림 생성을 완료했습니다."
        )
        return f"Summary created for {repo_name}."

    except GitCommandError as e:
        logger.error(
            f"[Sched Task] DB Task {task_id}: Git 클론 실패 '{repo_url}'. 오류: {e}"
        )
        return f"Git clone failed for {repo_url}."  # 재시도하지 않음
    except Exception as e:
        logger.error(
            f"[Sched Task] DB Task {task_id}: 요약 작업 중 오류 발생: {e}",
            exc_info=True,
        )
        raise self.retry(exc=e)


@celery_app.task
def check_and_run_user_tasks():
    """
    [Beat Task] 1분마다 DB의 `scheduled_tasks` 테이블을 스캔하여, 실행할 시간이 된
    사용자 정의 작업을 찾아 해당 태스크를 큐에 발행(dispatch)합니다.
    """
    logger.debug("[Beat Task] 사용자 정의 스케줄된 작업 스캔을 시작합니다...")

    select_tasks_stmt = text(
        "SELECT task_id, user_id, task_name, schedule, task_kwargs FROM scheduled_tasks WHERE is_active = true"
    )
    now = datetime.now()
    tasks_dispatched = 0

    try:
        with get_sync_db_session() as session:
            active_tasks = session.execute(select_tasks_stmt).fetchall()
            if not active_tasks:
                logger.debug("[Beat Task] 활성화된 사용자 작업이 없습니다.")
                return "No active user tasks to check."

            for task in active_tasks:
                task_dict = task._asdict()
                # croniter를 사용해 현재 시간이 cron 표현식과 일치하는지 확인
                if not croniter.is_now(task_dict["schedule"], now):
                    continue

                task_id = task_dict["task_id"]
                task_name = task_dict["task_name"]
                logger.info(
                    f"[Beat Task] DB Task {task_id} ('{task_name}')의 실행 시간이 되었습니다. 큐에 작업을 발행합니다."
                )

                # task_name에 따라 적절한 Celery 태스크를 호출합니다.
                if task_name == "run_scheduled_github_summary":
                    kwargs = task_dict.get("task_kwargs", {})
                    repo_url = kwargs.get("repo_url")
                    if repo_url:
                        run_scheduled_github_summary.delay(
                            task_id=task_id,
                            user_id=task_dict["user_id"],
                            repo_url=repo_url,
                        )
                        tasks_dispatched += 1
                # 여기에 다른 사용자 정의 태스크 핸들러를 추가할 수 있습니다.
    except Exception as e:
        logger.error(
            f"[Beat Task] 사용자 정의 스케줄 스캔 중 심각한 오류 발생: {e}",
            exc_info=True,
        )
        return f"Error during user task scan: {e}"

    if tasks_dispatched > 0:
        logger.info(
            f"[Beat Task] 스캔 완료. {tasks_dispatched}개의 사용자 작업을 큐에 발행했습니다."
        )
    return f"Scan complete. Dispatched {tasks_dispatched} user tasks."


@celery_app.task(max_retries=3)
def notify_admins(message: str):
    """[Celery Task] (거버넌스) 'admin' 권한 그룹을 가진 모든 사용자에게 알림을 보냅니다."""
    logger.info(f"관리자 알림 태스크 시작: {message}")
    with get_sync_db_session() as session:
        # 1. 'admin' 그룹 사용자 ID 조회
        admin_users = session.execute(
            text("SELECT user_id FROM users WHERE 'admin' = ANY(permission_groups)")
        ).fetchall()

        if not admin_users:
            logger.warning("알림을 보낼 관리자가 없습니다.")
            return

        notifications = [
            {"user_id": user.user_id, "message": message} for user in admin_users
        ]

        # 2. 알림 삽입
        session.execute(
            text(
                "INSERT INTO user_notifications (user_id, message) VALUES (:user_id, :message)"
            ),
            notifications,
        )
    logger.info(f"{len(notifications)}명의 관리자에게 알림을 보냈습니다.")


@celery_app.task(max_retries=3)
def notify_user(user_id: int, message: str):
    """[Celery Task] (거버넌스) 특정 사용자에게 알림을 보냅니다."""
    logger.info(f"사용자 {user_id} 알림 태스크 시작: {message}")
    with get_sync_db_session() as session:
        session.execute(
            text(
                "INSERT INTO user_notifications (user_id, message) VALUES (:user_id, :message)"
            ),
            [{"user_id": user_id, "message": message}],
        )
    logger.info(f"사용자 {user_id}에게 알림을 보냈습니다.")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def promote_to_kb(
    self,
    attachment_id: int,
    kb_doc_id: str,
    permission_groups: List[str],
    admin_user_id: int,
):
    """
    [Celery Task] (거버넌스) '승인'된 임시 파일을 '영구 지식 베이스(KB)'로 복사(승격)합니다.
    이 작업은 임시 청크 테이블에서 영구 청크 테이블로 데이터를 복사하며,
    재-임베딩 없이 순수 DB 작업으로 고속 처리됩니다.
    """
    task_id = self.request.id
    logger.info(
        f"--- [Celery Task ID: {task_id}] '지식 승격' 시작 (Attachment ID: {attachment_id} -> KB ID: {kb_doc_id}) ---"
    )

    components = _initialize_components_for_task()
    vector_store = components["vector_store"]

    async def do_promotion():
        if not hasattr(vector_store, "AsyncSessionLocal"):
            raise TypeError("Vector store is missing AsyncSessionLocal")

        async with vector_store.AsyncSessionLocal() as session:
            async with session.begin():
                # 1. 원본 첨부파일 정보 조회 (메타데이터 복사용)
                att_result = await session.execute(
                    select(db_models.SessionAttachment).where(
                        db_models.SessionAttachment.attachment_id == attachment_id
                    )
                )
                attachment = att_result.scalar_one_or_none()
                if not attachment:
                    raise ValueError(
                        f"Attachment ID {attachment_id}를 찾을 수 없습니다."
                    )

                # 2. 'documents' (영구) 테이블에 새 문서 레코드 생성
                new_document = db_models.Document(
                    doc_id=kb_doc_id,
                    source_type="promoted-file",
                    owner_user_id=admin_user_id,  # 소유권은 '승인한 관리자'
                    permission_groups=permission_groups,
                    extra_metadata={
                        "original_filename": attachment.file_name,
                        "original_uploader_user_id": attachment.user_id,
                        "promotion_admin_user_id": admin_user_id,
                        "promotion_date": datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                    },
                    promoted_from_attachment_id=attachment_id,  # 이력 추적
                )
                session.add(new_document)

                # 3. 'session_attachment_chunks' -> 'document_chunks'로 고속 복사
                # (재-임베딩이 필요 없는 순수 SQL 작업)
                stmt_copy_chunks = text(
                    f"""
                    INSERT INTO document_chunks (doc_id, chunk_text, embedding, extra_metadata)
                    SELECT
                        :kb_doc_id,  -- 새 영구 ID
                        chunk_text,
                        embedding,
                        extra_metadata
                    FROM
                        session_attachment_chunks
                    WHERE
                        attachment_id = :attachment_id
                    """
                )
                result = await session.execute(
                    stmt_copy_chunks,
                    {"kb_doc_id": kb_doc_id, "attachment_id": attachment_id},
                )
                copied_chunks_count = result.rowcount

                # 4. 원본 첨부파일 상태를 'promoted'로 업데이트
                attachment.status = "promoted"
                session.add(attachment)

                return copied_chunks_count

    try:
        copied_count = asyncio.run(do_promotion())

        success_message = f"'{kb_doc_id}'(으)로 지식 승격 완료. {copied_count}개 청크가 영구 KB로 복사되었습니다."
        logger.info(
            f"--- [Celery Task ID: {task_id}] '지식 승격' 성공: {success_message} ---"
        )
        return {
            "status": "success",
            "message": success_message,
            "copied_chunks": copied_count,
        }

    except Exception as e:
        logger.error(
            f"--- [Celery Task ID: {task_id}] '지식 승격' 중 심각한 오류 발생: {e} ---",
            exc_info=True,
        )
        # (향후 실패 시 DB 상태를 'failed'로 업데이트하는 로직 추가 권장)
        raise self.retry(exc=e)
