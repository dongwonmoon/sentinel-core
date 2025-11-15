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
from croniter import croniter
from datetime import datetime
from git import Repo
from git.exc import GitCommandError

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    Language,
)

# --- 1. 아키텍처에 따른 임포트 경로 수정 ---
from ..core.config import get_settings

settings = get_settings()
from ..components.llms.base import BaseLLM
from ..core import factories
from ..core import prompts
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


@contextmanager
def get_sync_db_session():
    engine = create_engine(settings.SYNC_DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"DB 세션 중 오류 발생! 롤백됩니다. {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


async def _generate_hypothetical_question(chunk_text: str, llm: BaseLLM) -> str:
    """LLM을 호출하여 청크에 대한 가상 질문을 생성합니다."""
    if not chunk_text.strip():
        return ""

    prompt = prompts.HYPOTHETICAL_QUESTION_PROMPT.format(chunk_text=chunk_text)
    try:
        response = await asyncio.wait_for(
            llm.invoke([HumanMessage(content=prompt)], config={}),
            timeout=10.0,  # 질문 생성은 10초 이내
        )
        question = response.content.strip().replace("?", "") + "?"
        logger.debug(f"HyDE: 원본(%.20s...) -> 질문(%s)", chunk_text, question)
        return question
    except Exception as e:
        logger.warning(f"HyDE: 가상 질문 생성 실패 (%.20s...): %s", chunk_text, e)
        return chunk_text


async def _load_and_split_documents(
    temp_file_path: str,
    file_name: str,
    text_splitter_default: RecursiveCharacterTextSplitter,
    llm: BaseLLM,
) -> List[Document]:
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
    split_chunks: List[Document] = []

    if language and language != Language.MARKDOWN:
        try:
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=language, chunk_size=1000, chunk_overlap=200
            )

            split_chunks = splitter.split_documents(docs)
        except Exception:
            logger.warning(
                f"CodeSplitter for {language.value} failed. Falling back to default."
            )
            split_chunks = text_splitter_default.split_documents(docs)
    else:
        split_chunks = text_splitter_default.split_documents(docs)

    tasks = []
    for chunk in split_chunks:
        tasks.append(_generate_hypothetical_question(chunk.page_content, llm))

    hypothetical_questions = await asyncio.gather(*tasks)

    # 메타데이터에 가상 질문(임베딩 소스) 저장
    final_docs_with_context = []
    for i, chunk in enumerate(split_chunks):
        hypo_question = hypothetical_questions[i]

        # 임베딩될 텍스트를 메타데이터에 저장합니다.
        # 실패 시 원본 텍스트가 저장되므로, 임베딩은 항상 유효합니다.
        chunk.metadata["embedding_source_text"] = hypo_question

        final_docs_with_context.append(chunk)

    return final_docs_with_context


# --- 3. Celery 태스크 정의 ---


@celery_app.task
def process_document_indexing(
    file_content: bytes,
    file_name: str,
    permission_groups: List[str],
    owner_user_id: int,
):
    """파일 내용을 받아 인덱싱하는 Celery 작업입니다."""
    logger.info(
        "--- [Celery Task] '%s' 인덱싱 시작 (권한=%s, 크기=%d바이트) ---",
        file_name,
        permission_groups,
        len(file_content),
        owner_user_id,
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
        fast_llm = factories.create_llm(
            settings.llm.fast, settings, settings.OPENAI_API_KEY
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
                                    fast_llm,
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
                    temp_file_path, file_name, text_splitter_default, fast_llm
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
                owner_user_id=owner_user_id,
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
    owner_user_id: int,
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
        fast_llm = factories.create_llm(
            settings.llm.fast, settings, settings.OPENAI_API_KEY
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
                                file_path,
                                relative_path,
                                text_splitter_default,
                                fast_llm,
                            )
                        )
                        doc_id = f"github-repo-{repo_name}/{relative_path}"
                        for chunk in chunks:
                            chunk.metadata["doc_id"] = doc_id
                            chunk.metadata["source_type"] = "github-repo"
                            chunk.metadata["repo_url"] = repo_url
                            chunk.metadata["repo_name"] = repo_name
                            chunk.metadata["source"] = relative_path
                            chunk.metadata["owner_user_id"] = owner_user_id

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
            documents=all_chunks_to_index,
            permission_groups=permission_groups,
            owner_user_id=owner_user_id,
        )
    )
    logger.info(f"--- [Celery Task] '{repo_name}' 인덱싱 완료 ---")
    return {
        "status": "success",
        "message": f"'{repo_name}' 처리 완료. (총 {total_files_processed}개 파일, {len(all_chunks_to_index)}개 청크 인덱싱)",
    }


@celery_app.task
def check_stale_documents(days_old: int = 180):
    """
    오래된 문서(e.g., 180일)를 스캔하여 소유자에게 알림을 보냅니다.
    Celery Beat에 의해 주기적으로 실행됩니다.
    """
    logger.info(f"[Beat Task] {days_old}일 이상된 오래된 문서 스캔 시작...")

    find_stale_stmt = text(
        f"""
        SELECT doc_id, owner_user_id, last_verified_at, metadata
        FROM documents
        WHERE last_verified_at < NOW() - INTERVAL '{days_old} days'
          AND owner_user_id IS NOT NULL
    """
    )

    insert_notification_stmt = text(
        f"""
        INSERT INTO user_notifications (user_id, message)
        VALUES (:user_id, :message)
    """
    )

    notifications_sent = 0
    try:
        with get_sync_db_session() as session:
            stale_documents = session.execute(find_stale_stmt).fetchall()

            if not stale_documents:
                logger.info(f"[Beat Task] 오래된 문서가 없습니다. 작업 완료.")
                return f"No stale documents found."

            logger.warning(
                f"[Beat Task] {len(stale_documents)}개의 오래된 문서를 발견. 알림 생성 시작..."
            )

            notifications_to_create = []
            for doc in stale_documents:
                doc_dict = doc._asdict()
                doc_name = (doc_dict.get("metadata", {}) or {}).get(
                    "original_zip"
                ) or doc_dict.get("doc_id")

                notifications_to_create.append(
                    {
                        "user_id": doc_dict["owner_user_id"],
                        "message": f"지식 소스 '{doc_name}'(이)가 {days_old}일 이상 검증되지 않았습니다. 관리 페이지에서 검증하거나 재업데이트해 주세요.",
                    }
                )

            if notifications_to_create:
                session.execute(insert_notification_stmt, notifications_to_create)
                notifications_sent = len(notifications_to_create)

    except Exception as e:
        logger.error(
            f"[Beat Task] 오래된 문서 스캔 중 심각한 오류 발생: {e}", exc_info=True
        )
        return f"Error during stale check: {e}"

    logger.info(f"[Beat Task] 스캔 완료. {notifications_sent}개의 알림 생성.")
    return f"Scan complete. Sent {notifications_sent} notifications."


@celery_app.task
def run_scheduled_github_summary(task_id: int, user_id: int, repo_url: str):
    """
    단일 GitHub 리포지토리의 최근 24시간 커밋을 요약하고 알림을 생성합니다.
    """
    logger.info(
        f"[Sched Task] Task {task_id} (User {user_id}): '{repo_url}' 요약 시작..."
    )

    try:
        # 1. LLM 및 DB 세션 준비
        settings = get_settings()
        fast_llm = factories.create_llm(
            settings.llm.fast, settings, settings.OPENAI_API_KEY
        )

        # 2. Git Log 가져오기 (최근 24시간)
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Repo.clone_from(repo_url, temp_dir, depth=50)  # 최근 50개 커밋만
            # 'since' 옵션을 사용해 최근 24시간 커밋만 필터링
            commits = list(repo.iter_commits(since="24.hours.ago"))

            if not commits:
                logger.info(
                    f"[Sched Task] Task {task_id}: '{repo_url}'에 새 커밋 없음."
                )
                return "No new commits found."

            commit_messages = "\n".join(
                [f"- {c.message.splitlines()[0]}" for c in commits]
            )

        # 3. LLM으로 요약
        prompt = prompts.SUMMARY_PROMPT_TEMPLATE.format(commit_messages=commit_messages)
        response = asyncio.run(
            fast_llm.invoke([HumanMessage(content=prompt)], config={})
        )
        summary = response.content.strip()

        # 4. user_notifications 테이블에 결과 저장
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        notification_message = f"데일리 요약: '{repo_name}'\n{summary}"

        insert_stmt = text(
            "INSERT INTO user_notifications (user_id, message) VALUES (:user_id, :message)"
        )
        with get_sync_db_session() as session:
            session.execute(
                insert_stmt, {"user_id": user_id, "message": notification_message}
            )

        logger.info(
            f"[Sched Task] Task {task_id}: '{repo_name}' 요약 완료. 알림 생성됨."
        )
        return f"Summary created for {repo_name}."

    except GitCommandError as e:
        logger.error(f"[Sched Task] Task {task_id}: Git 클론 실패 '{repo_url}'. {e}")
        # (선택) 실패 시에도 사용자에게 알림
    except Exception as e:
        logger.error(
            f"[Sched Task] Task {task_id}: 요약 작업 중 오류: {e}", exc_info=True
        )
        # (선택) 실패 시에도 사용자에게 알림


@celery_app.task
def check_and_run_user_tasks():
    """
    DB의 `scheduled_tasks` 테이블을 1분마다 스캔하여,
    실행할 시간이 된 사용자 정의 작업을 찾아 Celery 큐에 발행(dispatch)합니다.
    """
    logger.debug("[Beat Task] 사용자 정의 스케줄 스캔 시작...")

    select_tasks_stmt = text(
        """
        SELECT task_id, user_id, task_name, schedule, task_kwargs
        FROM scheduled_tasks
        WHERE is_active = true
    """
    )

    now = datetime.now()
    tasks_dispatched = 0

    try:
        with get_sync_db_session() as session:
            active_tasks = session.execute(select_tasks_stmt).fetchall()

            for task in active_tasks:
                task_dict = task._asdict()
                schedule_str = task_dict["schedule"]

                # 1. croniter를 사용해 지금 실행할 시간인지 확인
                if not croniter.is_now(schedule_str, now):
                    continue  # 실행 시간 아님

                task_name = task_dict["task_name"]
                task_id = task_dict["task_id"]
                user_id = task_dict["user_id"]
                kwargs = task_dict.get("task_kwargs", {})

                logger.info(
                    f"[Beat Task] Task {task_id} ('{task_name}') 실행 시간이 됨. 큐에 발행..."
                )

                # 2. (중요) task_name에 따라 실제 Celery Task를 동적으로 호출
                if task_name == "run_scheduled_github_summary":
                    repo_url = kwargs.get("repo_url")
                    if repo_url:
                        run_scheduled_github_summary.delay(
                            task_id=task_id, user_id=user_id, repo_url=repo_url
                        )
                        tasks_dispatched += 1

                # (추후 다른 task_name 추가 가능)
                # elif task_name == "run_some_other_task":
                #    ...

    except Exception as e:
        logger.error(
            f"[Beat Task] 사용자 정의 스케줄 스캔 중 심각한 오류 발생: {e}",
            exc_info=True,
        )
        return f"Error during user task scan: {e}"

    if tasks_dispatched > 0:
        logger.info(
            f"[Beat Task] 스캔 완료. {tasks_dispatched}개의 사용자 작업을 큐에 발행."
        )

    return f"Scan complete. Dispatched {tasks_dispatched} user tasks."
