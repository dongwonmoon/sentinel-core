# tasks.py
import asyncio
import os
import tempfile
from typing import List

from celery import Celery, Task
from celery.signals import worker_process_init
from langchain_community.document_loaders import (PyPDFLoader, TextLoader,
                                                  UnstructuredMarkdownLoader)
from langchain_text_splitters import RecursiveCharacterTextSplitter

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

# --- 3. Celery 워커 프로세스 초기화 ---
# Celery 워커는 별도의 프로세스에서 실행되므로, FastAPI 앱과는 독립적으로
# 필요한 컴포넌트(Vector Store, Embedding Model)를 초기화해야 합니다.

# 워커 프로세스별로 사용할 컴포넌트 인스턴스를 저장할 전역 변수
# (Task 클래스에서 이 변수를 참조합니다)
_vector_store_instance: BaseVectorStore = None

@worker_process_init.connect
def init_worker_components(**kwargs):
    """
    Celery 워커 프로세스가 시작될 때 한 번만 실행되는 함수입니다.
    이곳에서 Vector Store와 Embedding Model을 초기화합니다.
    """
    global _vector_store_instance
    logger.info("--- [Celery Worker] 컴포넌트 초기화 시작 ---")
    try:
        # main.py의 팩토리 함수를 재사용하여 컴포넌트를 생성합니다.
        embedding_model = get_embedding_model(settings)
        _vector_store_instance = get_vector_store(settings, embedding_model)
        logger.info("--- [Celery Worker] Vector Store 및 Embedding Model 초기화 완료 ---")
    except Exception as e:
        logger.error(f"--- [Celery Worker] 컴포넌트 초기화 실패: {e} ---", exc_info=True)
        _vector_store_instance = None


# --- 4. 인덱싱 작업 정의 ---

class IndexingTask(Task):
    """
    Task 클래스를 상속받아 커스텀 Task를 정의합니다.
    이를 통해 초기화된 vector_store에 self를 통해 접근할 수 있습니다.
    """
    @property
    def vector_store(self) -> BaseVectorStore:
        """워커 프로세스에 초기화된 vector_store 인스턴스를 반환합니다."""
        return _vector_store_instance

@celery_app.task(bind=True, base=IndexingTask, name="tasks.process_document_indexing")
def process_document_indexing(
    self: IndexingTask,  # `bind=True`로 인해 self(Task 인스턴스)를 첫 인자로 받음
    file_content: bytes,
    file_name: str,
    permission_groups: List[str],
):
    """
    파일 내용을 받아 인덱싱하는 Celery 작업입니다.
    """
    if not self.vector_store:
        logger.error("Celery 워커의 Vector Store가 초기화되지 않아 작업을 처리할 수 없습니다.")
        return {"status": "error", "message": "Celery 워커의 Vector Store가 초기화되지 않았습니다."}

    logger.info(f"--- [Celery Task] '{file_name}' 인덱싱 시작 ---")
    
    # 임시 파일을 안전하게 생성하고, 작업 완료 후 자동 삭제되도록 합니다.
    # NamedTemporaryFile은 컨텍스트를 벗어나면 자동으로 파일이 삭제됩니다.
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as tmp_file:
        tmp_file.write(file_content)
        temp_file_path = tmp_file.name

    try:
        # 1. 파일 타입에 따라 적절한 로더 선택
        file_ext = os.path.splitext(file_name)[1].lower()
        if file_ext == ".pdf":
            loader = PyPDFLoader(temp_file_path)
        elif file_ext == ".md":
            loader = UnstructuredMarkdownLoader(temp_file_path)
        elif file_ext == ".txt":
            loader = TextLoader(temp_file_path)
        else:
            raise ValueError(f"지원하지 않는 파일 형식: {file_ext}")

        docs = loader.load()

        # 2. 텍스트 분할 (Chunking)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_documents(docs)
        if not chunks:
            logger.warning(f"'{file_name}' 문서에서 텍스트를 추출하지 못했습니다.")
            return {"status": "error", "message": "문서에서 텍스트를 추출하지 못했습니다."}

        # 3. 문서 메타데이터 보강
        doc_id = f"file-upload-{file_name}"
        for chunk in chunks:
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["source_type"] = "file-upload"

        # 4. DB에 저장 (Upsert)
        # vector_store의 upsert_documents는 async 함수이므로, asyncio.run으로 실행합니다.
        asyncio.run(self.vector_store.upsert_documents(
            documents=chunks,
            permission_groups=permission_groups,
        ))

        logger.info(f"--- [Celery Task] '{file_name}' 인덱싱 완료 ---")
        return {"status": "success", "doc_id": doc_id, "chunks_indexed": len(chunks)}

    except Exception as e:
        logger.error(f"[Celery Task] '{file_name}' 인덱싱 중 에러 발생", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        # 작업 성공/실패와 관계없이 임시 파일을 항상 삭제합니다.
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)