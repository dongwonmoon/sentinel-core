import asyncio
import os
import tempfile
from typing import List
import json

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
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    except Exception as e:
        print(f"--- [Celery Task] ❌ 컴포넌트 초기화 실패: {e} ---")
        return {"status": "error", "message": f"컴포넌트 초기화 실패: {e}"}

    print(f"--- [Celery Task] '{file_name}' 인덱싱 시작 ---")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as tmp_file:
        tmp_file.write(file_content)
        temp_file_path = tmp_file.name

    try:
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

        chunks = text_splitter.split_documents(docs)
        if not chunks:
            return {"status": "error", "message": "문서에서 텍스트를 추출하지 못했습니다."}

        doc_id = f"file-upload-{file_name}"
        for chunk in chunks:
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["source_type"] = "file-upload"

        asyncio.run(vector_store.upsert_documents(
            documents=chunks,
            permission_groups=permission_groups,
        ))

        print(f"--- [Celery Task] '{file_name}' 인덱싱 완료 ---")
        return {"status": "success", "doc_id": doc_id, "chunks_indexed": len(chunks)}

    except Exception as e:
        print(f"❌ [Celery Task] 에러 발생: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)