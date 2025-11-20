# -*- coding: utf-8 -*-
"""
Celery 워커가 실제로 수행할 비동기 작업(Task)들을 정의합니다.

이 모듈의 함수들은 `@celery_app.task` 데코레이터를 통해 Celery 태스크로 등록됩니다.
API 서버의 응답 시간을 저하시키지 않으면서 시간이 오래 걸리는 작업들을
백그라운드에서 비동기적으로 처리하는 것이 주 목적입니다.

주요 태스크 종류:
- **임시 파일 인덱싱**: 사용자가 채팅 세션에 업로드한 단일 파일을 파싱해 청크/임베딩을 생성합니다.
- **로컬 디렉터리 인덱싱**: 브라우저에서 업로드된 다중 파일(폴더)을 ZIP으로 처리해 세션 전용 KB를 구축합니다.
- **GitHub 연동 인덱싱**: 지정한 리포지토리를 클론해 동일한 파이프라인으로 인덱싱합니다.
"""

import asyncio
import io
import json
import os
import tempfile
import zipfile
from typing import Any, Dict, List

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
from sqlalchemy import text

from ..components.llms.base import BaseLLM
from ..core import factories, prompts
from ..core.config import get_settings
from ..core.logger import get_logger
from .celery_app import celery_app

logger = get_logger(__name__)

# --- 헬퍼 함수 및 상수 ---

# 파일 확장자와 LangChain의 코드 분할기 언어 타입 매핑
# 코드 관련 확장자는 특정 언어용 스플리터를 사용하기 위함이며,
# .md는 일반 텍스트와 다른 자체 스플리터(UnstructuredMarkdownLoader)를 사용하므로 맵핑에 포함됩니다.
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


async def _generate_hypothetical_question(chunk_text: str, llm: BaseLLM) -> str:
    """
    [비동기 헬퍼] LLM을 호출하여 청크 내용에 기반한 가상 질문(Hypothetical Question)을 생성합니다.

    이 함수는 HyDE(Hypothetical Document Embeddings) 기법을 구현합니다.
    HyDE의 핵심 아이디어는 사용자의 실제 질문과 유사한 형태의 "가상" 질문을 생성하고,
    이 질문을 임베딩하여 벡터 검색에 사용하는 것입니다. 이렇게 하면 원본 문서 청크의
    임베딩보다 사용자 질문의 임베딩과 더 가까운 공간에 위치하게 되어 검색 정확도가
    향상될 수 있습니다.

    Args:
        chunk_text (str): 가상 질문을 생성할 원본 문서 청크의 텍스트.
        llm (BaseLLM): 가상 질문 생성을 위해 호출할 LLM 인스턴스.

    Returns:
        str: 생성된 가상 질문. 생성에 실패하거나 타임아웃이 발생하면 원본 청크 텍스트를 반환합니다.
    """
    # 내용이 없는 청크는 처리하지 않습니다.
    if not chunk_text.strip():
        return ""

    # 프롬프트에 청크 텍스트를 주입하여 LLM에 전달할 최종 프롬프트를 완성합니다.
    prompt = prompts.HYPOTHETICAL_QUESTION_PROMPT.format(chunk_text=chunk_text)
    try:
        # LLM 호출이 무한정 길어지는 것을 방지하기 위해 15초 타임아웃을 설정합니다.
        response = await asyncio.wait_for(
            llm.invoke([HumanMessage(content=prompt)], config={}), timeout=15.0
        )
        question = response.content.strip()
        logger.debug(
            f"HyDE 생성: 원본 '%.20s...' -> 질문 '%s'", chunk_text, question
        )
        return question
    except asyncio.TimeoutError:
        # 타임아웃 발생 시, 검색 품질 저하를 감수하고 원본 텍스트를 임베딩 소스로 사용합니다.
        logger.warning(
            f"HyDE: 가상 질문 생성 시간 초과 (원본: '%.20s...')", chunk_text
        )
        return chunk_text  # 실패 시 원본 텍스트를 그대로 반환하여 임베딩 소스로 사용
    except Exception as e:
        # 기타 예외 발생 시에도 원본 텍스트를 사용합니다.
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
    [비동기 헬퍼] 단일 파일을 로드하고 적절한 청크로 분할한 후, 각 청크에 대한 가상 질문(HyDE)을 생성합니다.

    이 함수는 파일 처리 파이프라인의 핵심적인 단계를 담당합니다.
    1. 파일 확장자를 기반으로 적절한 `DocumentLoader`를 선택하여 파일 내용을 로드합니다.
    2. 코드 파일의 경우, 구문 구조를 더 잘 이해하는 언어별 `TextSplitter`를 사용합니다.
       - 예를 들어, Python 코드의 경우 함수나 클래스 정의를 기준으로 분할을 시도합니다.
    3. 분할된 각 청크에 대해 `_generate_hypothetical_question`을 병렬로 호출하여
       HyDE(Hypothetical Document Embeddings)를 위한 가상 질문을 생성합니다.
    4. 최종적으로 각 `Document` 객체의 메타데이터에 생성된 가상 질문을 추가하여 반환합니다.

    Args:
        temp_file_path (str): 처리할 파일이 저장된 임시 경로.
        file_name (str): 사용자가 업로드한 원본 파일 이름 (확장자 판별에 사용).
        text_splitter_default (RecursiveCharacterTextSplitter): 기본적으로 사용할 텍스트 분할기.
        llm (BaseLLM): 가상 질문 생성을 위해 사용할 LLM.

    Returns:
        List[Document]: 각 청크의 원본 내용과 함께, 'embedding_source_text' 메타데이터에
                        가상 질문이 포함된 `Document` 객체의 리스트.
    """
    file_ext = os.path.splitext(file_name)[1].lower()
    logger.debug(
        f"문서 로드 및 분할 시작: 파일='{file_name}', 확장자='{file_ext}'"
    )

    # 1. 파일 확장자에 따라 적절한 로더 선택
    # PDF, Markdown 등 특정 형식에 맞는 파서를 사용하여 텍스트를 정확하게 추출합니다.
    if file_ext == ".pdf":
        loader = PyPDFLoader(temp_file_path)
    elif file_ext == ".md":
        loader = UnstructuredMarkdownLoader(temp_file_path)
    else:  # .txt, .py, .js 등 텍스트 기반 파일
        # 기타 파일은 일반 텍스트로 간주하고, 인코딩을 자동으로 감지하여 로드합니다.
        loader = TextLoader(temp_file_path, autodetect_encoding=True)

    docs = loader.load()

    # 2. 코드 파일의 경우, 언어에 특화된 스플리터 사용
    # CODE_LANGUAGE_MAP을 통해 파일 확장자에 해당하는 프로그래밍 언어를 찾습니다.
    language = CODE_LANGUAGE_MAP.get(file_ext)
    splitter = text_splitter_default
    if language and language != Language.MARKDOWN:
        try:
            # LangChain에서 제공하는 언어별 스플리터를 동적으로 생성합니다.
            # 이는 코드의 논리적 단위를 더 잘 보존하며 청크를 생성하는 데 도움이 됩니다.
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=language, chunk_size=1000, chunk_overlap=200
            )
            logger.debug(f"'{language.value}' 언어용 스플리터를 사용합니다.")
        except Exception:
            # 지원되지 않는 언어이거나 관련 라이브러리가 없는 경우, 경고를 남기고 기본 스플리터를 사용합니다.
            logger.warning(
                f"'{language.value}'용 코드 스플리터 사용 실패. 기본 스플리터로 대체합니다."
            )

    split_chunks = splitter.split_documents(docs)
    logger.debug(
        f"'{file_name}' 파일을 {len(split_chunks)}개의 청크로 분할했습니다."
    )

    # 3. 각 청크에 대해 가상 질문을 비동기적으로 병렬 생성 (HyDE)
    # asyncio.gather를 사용하여 여러 LLM 호출을 동시에 실행함으로써 전체 처리 시간을 단축합니다.
    tasks = [
        _generate_hypothetical_question(chunk.page_content, llm)
        for chunk in split_chunks
    ]
    hypothetical_questions = await asyncio.gather(*tasks)

    # 4. 최종적으로 반환할 문서 목록에 가상 질문을 메타데이터로 추가
    # 이 'embedding_source_text'는 이후 임베딩 모델에 전달될 텍스트가 됩니다.
    final_docs = []
    for i, chunk in enumerate(split_chunks):
        chunk.metadata["embedding_source_text"] = hypothetical_questions[i]
        final_docs.append(chunk)

    return final_docs


def _initialize_components_for_task() -> Dict[str, Any]:
    """
    Celery 태스크 실행에 필요한 핵심 컴포넌트들을 초기화하고 딕셔너리 형태로 반환합니다.

    Celery 워커는 API 서버와는 별개의 독립적인 프로세스에서 실행됩니다.
    따라서 API 서버가 가진 컴포넌트(LLM, 벡터 저장소 등)의 인스턴스를 공유할 수 없습니다.
    이 함수는 각 태스크가 실행될 때마다 설정(config.yml)을 다시 읽어
    필요한 모든 컴포넌트를 새로 생성하는 역할을 합니다.

    Returns:
        Dict[str, Any]: 초기화된 컴포넌트들을 담은 딕셔너리.
                        - "embedding_model": 임베딩 생성을 위한 모델.
                        - "vector_store": 청크와 임베딩을 저장/검색하기 위한 벡터 저장소.
                        - "fast_llm": HyDE 등 빠른 응답이 필요한 곳에 사용할 LLM.
                        - "text_splitter_default": 기본 텍스트 분할기.
    """
    logger.debug("Celery 태스크를 위한 컴포넌트 초기화를 시작합니다.")
    settings = get_settings()

    # 설정 파일(config.yml)을 기반으로 팩토리 함수를 사용하여 각 컴포넌트를 생성합니다.
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
    [Celery Task] (신규) 세션에 첨부된 디렉토리(ZIP)를 인덱싱하여 'Session KB'에 저장합니다.
    (process_document_indexing 로직 재활용)
    ZIP 압축 해제 → 파일별 청크/임베딩 → session_attachment_chunks 저장 순으로 처리합니다.
    """
    task_id = self.request.id
    logger.info(
        f"--- [Celery Task ID: {task_id}] '세션 디렉토리' 인덱싱 시작 (Attachment ID: {attachment_id}, 이름: {display_name}) ---"
    )

    try:
        components = _initialize_components_for_task()
        vector_store = components["vector_store"]
        fast_llm = components["fast_llm"]
        text_splitter_default = components["text_splitter_default"]
        all_chunks_to_index = []

        # 1. ZIP 파일 처리 (기존 로직과 동일)
        with tempfile.TemporaryDirectory() as temp_dir:
            with io.BytesIO(zip_content) as zip_buffer:
                with zipfile.ZipFile(zip_buffer, "r") as zf:
                    zf.extractall(temp_dir)

            for root, _, files in os.walk(temp_dir):
                # ... (숨김 파일 등 건너뛰기 로직) ...
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
                        # [세션 KB용 수정] 메타데이터에 원본 디렉토리 이름 추가
                        for chunk in chunks:
                            chunk.metadata.update(
                                {
                                    "source_type": "session-directory",
                                    "original_group": display_name,
                                    "source": relative_path,
                                }
                            )
                        all_chunks_to_index.extend(chunks)
                    except Exception as e:
                        logger.warning(
                            f"디렉토리 내 파일 '{relative_path}' 처리 중 오류: {e}"
                        )

        if not all_chunks_to_index:
            logger.warning(
                f"'{display_name}' 처리 후 인덱싱할 청크가 없습니다."
            )
            return {"status": "warning", "message": "No content to index."}

        # 2. 임베딩 생성 (기존 로직과 동일)
        embedding_source_texts = [
            chunk.metadata.get("embedding_source_text", chunk.page_content)
            for chunk in all_chunks_to_index
        ]
        chunk_embeddings = vector_store.embedding_model.embed_documents(
            embedding_source_texts
        )

        # 3. [핵심 수정] 'session_attachment_chunks' 테이블에 저장
        # (process_session_attachment_indexing의 저장 로직 재활용)
        chunks_to_store = [
            {
                "attachment_id": attachment_id,
                "chunk_text": chunk.page_content,
                "embedding": str(embedding_vector),
                "extra_metadata": json.dumps(chunk.metadata),
            }
            for chunk, embedding_vector in zip(
                all_chunks_to_index, chunk_embeddings
            )
        ]

        async def save_chunks_to_db():
            if not hasattr(vector_store, "AsyncSessionLocal"):
                raise TypeError("Vector store is missing AsyncSessionLocal")
            async with vector_store.AsyncSessionLocal() as session:
                async with session.begin():
                    # 3a. 청크 삽입
                    stmt_chunks_insert = text(
                        """
                        INSERT INTO session_attachment_chunks
                        (attachment_id, chunk_text, embedding, extra_metadata)
                        VALUES (:attachment_id, :chunk_text, :embedding, :extra_metadata)
                        """
                    )
                    await session.execute(stmt_chunks_insert, chunks_to_store)
                    # 3b. 부모 Attachment 상태를 'temporary'로 업데이트
                    stmt_update_status = text(
                        "UPDATE session_attachments SET status = 'temporary' WHERE attachment_id = :attachment_id"
                    )
                    await session.execute(
                        stmt_update_status, {"attachment_id": attachment_id}
                    )

        asyncio.run(save_chunks_to_db())

        success_message = f"'{display_name}' 디렉토리 인덱싱 완료. {len(chunks_to_store)}개 청크 저장됨."
        logger.info(
            f"--- [Celery Task ID: {task_id}] 세션 디렉토리 인덱싱 성공 ---"
        )
        return {"status": "success", "message": success_message}

    except Exception as e:
        logger.error(
            f"--- [Celery Task ID: {task_id}] '{display_name}' 인덱싱 중 오류: {e} ---",
            exc_info=True,
        )
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def process_session_github_indexing(self, attachment_id: int, repo_url: str):
    """
    [Celery Task] (신규) 세션에 첨부된 GitHub 리포지토리를 인덱싱하여 'Session KB'에 저장합니다.
    클론 → 파일 청크 → 임베딩 → session_attachment_chunks 저장 순으로 진행합니다.
    (process_github_repo_indexing 로직 재활용)
    """
    task_id = self.request.id
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    logger.info(
        f"--- [Celery Task ID: {task_id}] '세션 GitHub' 인덱싱 시작 (Attachment ID: {attachment_id}, 레포: {repo_name}) ---"
    )

    try:
        components = _initialize_components_for_task()
        vector_store = components["vector_store"]
        fast_llm = components["fast_llm"]
        text_splitter_default = components["text_splitter_default"]
        all_chunks_to_index = []

        # 1. GitHub 클론 및 파일 처리 (기존 로직과 동일)
        with tempfile.TemporaryDirectory() as temp_dir:
            Repo.clone_from(repo_url, temp_dir, depth=50)
            for root, _, files in os.walk(temp_dir):
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
                        # [세션 KB용 수정] 메타데이터 변경
                        for chunk in chunks:
                            chunk.metadata.update(
                                {
                                    "source_type": "session-github",
                                    "repo_url": repo_url,
                                    "repo_name": repo_name,
                                    "source": relative_path,
                                }
                            )
                        all_chunks_to_index.extend(chunks)
                    except Exception as e:
                        logger.warning(
                            f"GitHub 리포지토리 내 파일 '{relative_path}' 처리 중 오류: {e}"
                        )

        if not all_chunks_to_index:
            logger.warning(
                f"'{repo_name}' 리포지토리에서 인덱싱할 콘텐츠가 없습니다."
            )
            return {
                "status": "warning",
                "message": "No content could be indexed.",
            }

        # 2. 임베딩 생성 (기존 로직과 동일)
        embedding_source_texts = [
            chunk.metadata.get("embedding_source_text", chunk.page_content)
            for chunk in all_chunks_to_index
        ]
        chunk_embeddings = vector_store.embedding_model.embed_documents(
            embedding_source_texts
        )

        # 3. [핵심 수정] 'session_attachment_chunks' 테이블에 저장
        # (process_session_directory_indexing의 저장 로직과 동일)
        chunks_to_store = [
            {
                "attachment_id": attachment_id,
                "chunk_text": chunk.page_content,
                "embedding": str(embedding_vector),
                "extra_metadata": json.dumps(chunk.metadata),
            }
            for chunk, embedding_vector in zip(
                all_chunks_to_index, chunk_embeddings
            )
        ]

        async def save_chunks_to_db():
            if not hasattr(vector_store, "AsyncSessionLocal"):
                raise TypeError("Vector store is missing AsyncSessionLocal")
            async with vector_store.AsyncSessionLocal() as session:
                async with session.begin():
                    stmt_chunks_insert = text(
                        """
                        INSERT INTO session_attachment_chunks
                        (attachment_id, chunk_text, embedding, extra_metadata)
                        VALUES (:attachment_id, :chunk_text, :embedding, :extra_metadata)
                        """
                    )
                    await session.execute(stmt_chunks_insert, chunks_to_store)
                    stmt_update_status = text(
                        "UPDATE session_attachments SET status = 'temporary' WHERE attachment_id = :attachment_id"
                    )
                    await session.execute(
                        stmt_update_status, {"attachment_id": attachment_id}
                    )

        asyncio.run(save_chunks_to_db())

        success_message = f"'{repo_name}' 리포지토리 인덱싱 완료. {len(chunks_to_store)}개 청크 저장됨."
        logger.info(
            f"--- [Celery Task ID: {task_id}] 세션 GitHub 인덱싱 성공 ---"
        )
        return {"status": "success", "message": success_message}

    except GitCommandError as e:
        logger.error(
            f"--- [Celery Task ID: {task_id}] Git 클론 실패: {repo_url}. 오류: {e} ---"
        )
        return {"status": "error", "message": "Failed to clone repository."}
    except Exception as e:
        logger.error(
            f"--- [Celery Task ID: {task_id}] '{repo_name}' 인덱싱 중 오류: {e} ---",
            exc_info=True,
        )
        raise self.retry(exc=e)
