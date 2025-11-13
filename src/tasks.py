import asyncio
import os
import tempfile
from typing import List
import json
import zipfile
import io
import tempfile
from git import Repo

from celery import Celery, Task
from celery.signals import worker_process_init
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    Language,
)

# --- 1. 설정 및 추상화 모듈 임포트 ---
from .config import settings
from .factories import get_embedding_model, get_vector_store
from .store.base import BaseVectorStore
from .logger import get_logger

logger = get_logger(__name__)

# --- 2. Celery 앱 설정 ---
# config.py의 settings 객체를 사용하여 Broker 및 Backend URL을 설정합니다.
celery_app = Celery(
    "sentinel_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

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


async def _load_and_split_documents(
    temp_file_path: str,
    file_name: str,
    text_splitter_default: RecursiveCharacterTextSplitter,
) -> List[any]:  # List[Document]
    """
    단일 파일 경로와 이름을 받아, 적절한 로더와 스플리터를 선택하여 문서를 분할합니다.
    """
    file_ext = os.path.splitext(file_name)[1].lower()

    # 1. 로더(Loader) 선택
    if file_ext == ".pdf":
        loader = PyPDFLoader(temp_file_path)
    elif file_ext == ".md":
        loader = UnstructuredMarkdownLoader(temp_file_path)
    elif file_ext == ".txt":
        loader = TextLoader(temp_file_path)
    # 코드 파일 처리
    elif file_ext in CODE_LANGUAGE_MAP or file_ext in [
        ".log",
        ".toml",
        ".yml",
        ".yaml",
    ]:
        loader = TextLoader(temp_file_path)
    else:
        # 지원하지 않는 형식 대신 일단 TextLoader로 시도
        logger.warning(
            f"지원하지 않는 파일 형식({file_ext})이지만 TextLoader로 시도: {file_name}"
        )
        loader = TextLoader(temp_file_path)

    docs = loader.load()

    # 2. 스플리터(Splitter) 선택
    language = CODE_LANGUAGE_MAP.get(file_ext)

    if language and language != Language.MARKDOWN:
        # 코드 스플리터 사용
        logger.info(
            f"'{file_name}'에 RecursiveCharacterTextSplitter.from_language ({language.value}) 적용"
        )
        try:
            code_splitter = (
                RecursiveCharacterTextSplitter.from_language(  # <-- [핵심 수정]
                    language=language, chunk_size=1000, chunk_overlap=200
                )
            )
            chunks = code_splitter.split_documents(docs)
        except Exception as e:
            # tree-sitter 등이 설치되지 않아 실패할 경우를 대비한 Fallback
            logger.warning(
                f"CodeSplitter.from_language 실패 ({e}). 기본 스플리터로 Fallback합니다."
            )
            chunks = text_splitter_default.split_documents(docs)
    else:
        # 기본 스플리터 사용 (PDF, TXT, MD 등)
        logger.info(f"'{file_name}'에 기본 TextSplitter 적용")
        chunks = text_splitter_default.split_documents(docs)

    return chunks


@celery_app.task(name="tasks.process_document_indexing")
def process_document_indexing(
    file_content: bytes,
    file_name: str,
    permission_groups: List[str],
):
    """
    파일 내용을 받아 인덱싱하는 Celery 작업입니다.
    """
    try:
        embedding_model = get_embedding_model(settings)
        vector_store = get_vector_store(settings, embedding_model)
        text_splitter_default = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
    except Exception as e:
        print(f"--- [Celery Task] ❌ 컴포넌트 초기화 실패: {e} ---")
        return {"status": "error", "message": f"컴포넌트 초기화 실패: {e}"}

    print(f"--- [Celery Task] '{file_name}' 인덱싱 시작 ---")

    all_chunks_to_index = []
    temp_files_to_clean = []
    total_files_processed = 0

    try:
        # --- ZIP 파일 처리 로직 ---
        if file_name.lower().endswith(".zip"):
            logger.info(
                f"'{file_name}'은 ZIP 파일입니다. 압축 해제 및 개별 인덱싱 시작..."
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                with io.BytesIO(file_content) as zip_buffer:
                    with zipfile.ZipFile(zip_buffer, "r") as zf:
                        zf.extractall(temp_dir)

                # 압축 해제된 폴더를 순회하며 모든 파일 인덱싱
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # 원본 ZIP 파일 내의 상대 경로로 file_name 구성 (메타데이터용)
                        relative_path = os.path.relpath(file_path, temp_dir)
                        # .git, .vscode, __pycache__ 등 무시
                        if (
                            any(
                                part.startswith(".")
                                for part in relative_path.split(os.sep)
                            )
                            or "__pycache__" in relative_path
                        ):
                            logger.info(f"무시: {relative_path}")
                            continue

                        try:
                            # 개별 파일을 로드하고 분할
                            chunks = asyncio.run(
                                _load_and_split_documents(
                                    file_path,
                                    relative_path,  # file_name 대신 상대 경로 사용
                                    text_splitter_default,
                                )
                            )

                            # ZIP 파일의 메타데이터 추가
                            doc_id = f"file-upload-{file_name}/{relative_path}"
                            for chunk in chunks:
                                chunk.metadata["doc_id"] = doc_id
                                chunk.metadata["source_type"] = "file-upload-zip"
                                chunk.metadata["original_zip"] = file_name
                                chunk.metadata["source"] = (
                                    relative_path  # 기존 source를 덮어씀
                                )

                            all_chunks_to_index.extend(chunks)
                            total_files_processed += 1

                        except Exception as e:
                            logger.warning(
                                f"❌ ZIP 내 파일 '{relative_path}' 처리 실패: {e}"
                            )

        else:
            # --- 단일 파일 처리 로직 ---
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{file_name}"
            ) as tmp_file:
                tmp_file.write(file_content)
                temp_file_path = tmp_file.name
                temp_files_to_clean.append(temp_file_path)

            chunks = asyncio.run(
                _load_and_split_documents(
                    temp_file_path, file_name, text_splitter_default
                )
            )

            doc_id = f"file-upload-{file_name}"
            for chunk in chunks:
                chunk.metadata["doc_id"] = doc_id
                chunk.metadata["source_type"] = "file-upload"
                chunk.metadata["source"] = file_name
                chunk.metadata["original_zip"] = None

            all_chunks_to_index.extend(chunks)
            total_files_processed = 1

        # --- 공통 Upsert 로직 ---
        if not all_chunks_to_index:
            logger.warning("문서에서 텍스트를 추출하지 못했습니다.")
            return {
                "status": "error",
                "message": "문서에서 텍스트를 추출하지 못했습니다.",
            }

        asyncio.run(
            vector_store.upsert_documents(
                documents=all_chunks_to_index,
                permission_groups=permission_groups,
            )
        )

        logger.info(f"--- [Celery Task] '{file_name}' 인덱싱 완료 ---")
        return {
            "status": "success",
            "message": f"'{file_name}' 처리 완료. (총 {total_files_processed}개 파일, {len(all_chunks_to_index)}개 청크 인덱싱)",
            "chunks_indexed": len(all_chunks_to_index),
        }

    except Exception as e:
        logger.error(
            f"❌ [Celery Task] '{file_name}' 인덱싱 중 에러 발생: {e}", exc_info=True
        )
        return {"status": "error", "message": str(e)}
    finally:
        for temp_file in temp_files_to_clean:
            if os.path.exists(temp_file):
                os.remove(temp_file)


@celery_app.task(name="tasks.process_github_repo_indexing")
def process_github_repo_indexing(
    repo_url: str,
    permission_groups: List[str],
):
    """
    GitHub 저장소를 클론하고, 내부 파일들을 인덱싱하는 Celery 작업입니다.
    """
    try:
        embedding_model = get_embedding_model(settings)
        vector_store = get_vector_store(settings, embedding_model)
        text_splitter_default = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
    except Exception as e:
        logger.error(f"--- [Celery Task] ❌ 컴포넌트 초기화 실패: {e} ---")
        return {"status": "error", "message": f"컴포넌트 초기화 실패: {e}"}

    repo_name = repo_url.split("/")[-1].replace(".git", "")
    logger.info(f"--- [Celery Task] '{repo_name}' ({repo_url}) 클론 시작 ---")

    all_chunks_to_index = []
    total_files_processed = 0

    # Git Clone을 위한 임시 디렉토리 생성
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # 1. Git Clone 수행
            Repo.clone_from(repo_url, temp_dir)
            logger.info(f"'{repo_name}' 클론 완료. 경로: {temp_dir}")

            # 2. ZIP 파일 처리 로직과 동일하게 폴더 순회
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # 클론된 디렉토리 기준 상대 경로 (메타데이터용)
                    relative_path = os.path.relpath(file_path, temp_dir)

                    # .git, .vscode 등 무시
                    if (
                        any(
                            part.startswith(".") for part in relative_path.split(os.sep)
                        )
                        or "__pycache__" in relative_path
                    ):
                        # logger.debug(f"무시: {relative_path}")
                        continue

                    try:
                        # 3. 기존 헬퍼 함수로 파일 로드 및 분할
                        chunks = asyncio.run(
                            _load_and_split_documents(
                                file_path,
                                relative_path,  # file_name 대신 상대 경로 사용
                                text_splitter_default,
                            )
                        )

                        # 4. GitHub용 메타데이터 추가
                        doc_id = f"github-repo-{repo_name}/{relative_path}"
                        for chunk in chunks:
                            chunk.metadata["doc_id"] = doc_id
                            chunk.metadata["source_type"] = "github-repo"
                            chunk.metadata["repo_url"] = repo_url
                            chunk.metadata["repo_name"] = repo_name
                            chunk.metadata["source"] = relative_path

                        all_chunks_to_index.extend(chunks)
                        total_files_processed += 1

                    except Exception as e:
                        logger.warning(
                            f"❌ GitHub 레포 내 파일 '{relative_path}' 처리 실패: {e}"
                        )

        except Exception as e:
            logger.error(
                f"❌ [Celery Task] '{repo_name}' 클론 또는 처리 중 에러: {e}",
                exc_info=True,
            )
            return {"status": "error", "message": f"Git Clone 또는 파일 처리 실패: {e}"}

    # --- 공통 Upsert 로직 ---
    if not all_chunks_to_index:
        logger.warning("레포지토리에서 텍스트를 추출하지 못했습니다.")
        return {
            "status": "error",
            "message": "레포지토리에서 텍스트를 추출하지 못했습니다.",
        }

    asyncio.run(
        vector_store.upsert_documents(
            documents=all_chunks_to_index,
            permission_groups=permission_groups,
        )
    )

    logger.info(f"--- [Celery Task] '{repo_name}' 인덱싱 완료 ---")
    return {
        "status": "success",
        "message": f"'{repo_name}' 처리 완료. (총 {total_files_processed}개 파일, {len(all_chunks_to_index)}개 청크 인덱싱)",
        "chunks_indexed": len(all_chunks_to_index),
    }
