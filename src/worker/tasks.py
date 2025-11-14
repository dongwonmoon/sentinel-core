"""
Celery 워커가 실제로 수행할 비동기 작업(Task)들을 정의합니다.
- 문서 인덱싱
- GitHub 저장소 인덱싱
"""

import asyncio
import os
import tempfile
from typing import List
import zipfile
import io
from git import Repo

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    Language,
)

# --- 1. 아키텍처에 따른 임포트 경로 수정 ---
from ..core.config import get_settings

settings = get_settings()
from ..core import factories
from ..core.logger import get_logger
from .celery_app import celery_app  # 생성된 Celery 앱 인스턴스를 임포트


logger = get_logger(__name__)


# --- 2. 헬퍼 함수 및 상수 정의 ---

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
) -> List[any]:
    """파일을 종류에 맞는 로더와 스플리터로 분할합니다."""
    file_ext = os.path.splitext(file_name)[1].lower()
    logger.debug("문서 스플릿 준비 - 파일='%s', 확장자='%s'", file_name, file_ext)

    if file_ext == ".pdf":
        loader = PyPDFLoader(temp_file_path)
    elif file_ext == ".md":
        loader = UnstructuredMarkdownLoader(temp_file_path)
    else:  # .txt 및 기타 코드 파일들
        loader = TextLoader(temp_file_path, autodetect_encoding=True)

    docs = loader.load()
    language = CODE_LANGUAGE_MAP.get(file_ext)

    if language and language != Language.MARKDOWN:
        try:
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=language, chunk_size=1000, chunk_overlap=200
            )
            return splitter.split_documents(docs)
        except Exception:
            logger.warning(
                f"CodeSplitter for {language.value} failed. Falling back to default."
            )
            return text_splitter_default.split_documents(docs)
    else:
        return text_splitter_default.split_documents(docs)


# --- 3. Celery 태스크 정의 ---


@celery_app.task
def process_document_indexing(
    file_content: bytes,
    file_name: str,
    permission_groups: List[str],
):
    """파일 내용을 받아 인덱싱하는 Celery 작업입니다."""
    logger.info(
        "--- [Celery Task] '%s' 인덱싱 시작 (권한=%s, 크기=%d바이트) ---",
        file_name,
        permission_groups,
        len(file_content),
    )
    try:
        # 새로운 팩토리 함수 시그니처에 맞게 컴포넌트 초기화
        embedding_model = factories.create_embedding_model(
            embedding_settings=settings.embedding,
            full_settings=settings,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        vector_store = factories.create_vector_store(
            settings.vector_store, settings, embedding_model
        )
        text_splitter_default = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
    except Exception as e:
        logger.error(f"--- [Celery Task] 컴포넌트 초기화 실패: {e} ---", exc_info=True)
        return {
            "status": "error",
            "message": f"Component initialization failed: {e}",
        }

    all_chunks_to_index = []
    total_files_processed = 0

    try:
        if file_name.lower().endswith(".zip"):
            # ZIP 파일 처리
            with tempfile.TemporaryDirectory() as temp_dir:
                with io.BytesIO(file_content) as zip_buffer:
                    with zipfile.ZipFile(zip_buffer, "r") as zf:
                        zf.extractall(temp_dir)

                all_files_found = []
                filtered_files_log = []
                processed_files_log = []

                logger.info(f"--- [DEBUG] Starting os.walk for '{temp_dir}' ---")

                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, temp_dir)

                        all_files_found.append(relative_path)
                        logger.debug(f"Walker: Found file: '{relative_path}'")

                        path_parts = relative_path.split(os.path.sep)
                        is_hidden = any(part.startswith(".") for part in path_parts)
                        is_pycache = "__pycache__" in relative_path

                        if is_hidden or is_pycache:
                            filtered_files_log.append(relative_path)
                            logger.debug(f"Walker: Filtered file: '{relative_path}'")
                            filtered_files_log.append(relative_path)
                            continue

                        try:
                            chunks = asyncio.run(
                                _load_and_split_documents(
                                    file_path,
                                    relative_path,
                                    text_splitter_default,
                                )
                            )
                            base_doc_id_prefix = file_name.rsplit(".zip", 1)[0]
                            doc_id = f"file-upload-{base_doc_id_prefix}/{relative_path}"
                            for chunk in chunks:
                                chunk.metadata["doc_id"] = doc_id
                                chunk.metadata["source_type"] = "file-upload-zip"
                                chunk.metadata["original_zip"] = base_doc_id_prefix
                                chunk.metadata["source"] = relative_path

                            all_chunks_to_index.extend(chunks)
                            total_files_processed += 1
                            logger.debug(
                                "ZIP 내 파일 처리 완료 - %s (청크 %d개)",
                                relative_path,
                                len(chunks),
                            )
                        except Exception as e:
                            logger.warning(
                                f"❌ ZIP 내 파일 '{relative_path}' 처리 실패: {e}"
                            )
        else:
            # 단일 파일 처리
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{file_name}"
            ) as tmp_file:
                tmp_file.write(file_content)
                temp_file_path = tmp_file.name

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
            all_chunks_to_index.extend(chunks)
            total_files_processed = 1
            os.remove(temp_file_path)
            logger.debug(
                "단일 파일 처리 완료 - doc_id=%s, 청크=%d개", doc_id, len(chunks)
            )

        if total_files_processed == 0:
            if not all_files_found and file_name.lower().endswith(".zip"):
                # ZIP은 열렸지만 `os.walk`가 아무 파일도 찾지 못함 (e.g., 비어있음)
                logger.error(
                    f"No files were found inside the ZIP archive '{file_name}'. It might be empty."
                )
                raise ValueError(
                    f"No files were found inside the ZIP archive '{file_name}'. It might be empty."
                )

            elif filtered_files_log and not processed_files_log:
                # 모든 파일이 필터링됨
                logger.error(
                    f"All {len(all_files_found)} files in '{file_name}' were filtered. "
                    f"Filtered examples: {filtered_files_log[:5]}"
                )
                raise ValueError(
                    f"No files were processed. All {len(all_files_found)} files were filtered "
                    f"(e.g., .git, .venv, __pycache__, or Mac resource forks like '._filename')."
                )

            elif processed_files_log and not all_chunks_to_index:
                # 텍스트 추출 실패
                logger.error(
                    f"Processed {len(processed_files_log)} file(s) from '{file_name}', but no text was extracted. "
                    f"Files attempted: {processed_files_log[:5]}"
                )
                raise ValueError(
                    f"Processed {len(processed_files_log)} file(s), but no text could be extracted. "
                    f"The files might be non-text (e.g., images) or empty."
                )

            else:
                # 그 외 (e.g., 단일 파일 업로드인데 텍스트 추출 실패 등)
                logger.error(
                    f"Unknown state: {len(all_files_found)} found, {len(filtered_files_log)} filtered, {len(processed_files_log)} processed, 0 chunks."
                )
                raise ValueError(
                    f"No files were processed. The archive '{file_name}' is empty or contains no valid files."
                )

        asyncio.run(
            vector_store.upsert_documents(
                documents=all_chunks_to_index,
                permission_groups=permission_groups,
            )
        )
        logger.info(f"--- [Celery Task] '{file_name}' 인덱싱 완료 ---")
        return {
            "status": "success",
            "message": f"Processed '{file_name}'. Indexed {len(all_chunks_to_index)} chunks from {total_files_processed} file(s).",
        }
    except Exception as e:
        logger.error(
            f"--- [Celery Task] '{file_name}' 인덱싱 중 에러: {e} ---",
            exc_info=True,
        )
        return {"status": "error", "message": str(e)}


@celery_app.task
def process_github_repo_indexing(
    repo_url: str,
    permission_groups: List[str],
):
    """GitHub 저장소를 클론하고, 내부 파일들을 인덱싱하는 Celery 작업입니다."""
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    logger.info(
        "--- [Celery Task] '%s' (%s) 클론 및 인덱싱 시작 (권한=%s) ---",
        repo_name,
        repo_url,
        permission_groups,
    )

    try:
        embedding_model = factories.create_embedding_model(
            embedding_settings=settings.embedding,
            full_settings=settings,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        vector_store = factories.create_vector_store(
            settings.vector_store, settings, embedding_model
        )
        text_splitter_default = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
    except Exception as e:
        logger.error(f"--- [Celery Task] 컴포넌트 초기화 실패: {e} ---", exc_info=True)
        return {
            "status": "error",
            "message": f"Component initialization failed: {e}",
        }

    all_chunks_to_index = []
    total_files_processed = 0

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            Repo.clone_from(repo_url, temp_dir)
            logger.info(f"'{repo_name}' 클론 완료. 경로: {temp_dir}")

            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if ".git" in root:
                        continue

                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, temp_dir)

                    try:
                        chunks = asyncio.run(
                            _load_and_split_documents(
                                file_path, relative_path, text_splitter_default
                            )
                        )
                        doc_id = f"github-repo-{repo_name}/{relative_path}"
                        for chunk in chunks:
                            chunk.metadata["doc_id"] = doc_id
                            chunk.metadata["source_type"] = "github-repo"
                            chunk.metadata["repo_url"] = repo_url
                            chunk.metadata["repo_name"] = repo_name
                            chunk.metadata["source"] = relative_path

                        all_chunks_to_index.extend(chunks)
                        total_files_processed += 1
                        logger.debug(
                            "GitHub 파일 처리 완료 - %s (청크 %d개)",
                            relative_path,
                            len(chunks),
                        )
                    except Exception as e:
                        logger.warning(
                            f"❌ GitHub 레포 내 파일 '{relative_path}' 처리 실패: {e}"
                        )

        except Exception as e:
            logger.error(
                f"❌ [Celery Task] '{repo_name}' 클론 또는 처리 중 에러: {e}",
                exc_info=True,
            )
            return {
                "status": "error",
                "message": f"Git Clone 또는 파일 처리 실패: {e}",
            }

    if not all_chunks_to_index:
        logger.warning("레포지토리에서 텍스트를 추출하지 못했습니다.")
        return {
            "status": "error",
            "message": "레포지토리에서 텍스트를 추출하지 못했습니다.",
        }

    asyncio.run(
        vector_store.upsert_documents(
            documents=all_chunks_to_index, permission_groups=permission_groups
        )
    )
    logger.info(f"--- [Celery Task] '{repo_name}' 인덱싱 완료 ---")
    return {
        "status": "success",
        "message": f"'{repo_name}' 처리 완료. (총 {total_files_processed}개 파일, {len(all_chunks_to_index)}개 청크 인덱싱)",
    }
