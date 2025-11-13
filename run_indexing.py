import os
import numpy as np
from typing import List, Dict, Any
from langchain_community.document_loaders import DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama.embeddings import OllamaEmbeddings

from src.config import settings
from src.store.pg_vector_store import PGVectorStore

# --- 1. 설정 (Configuration) ---
DB_URL = settings.SYNC_DATABASE_URL
DATA_PATH = os.path.join(os.path.dirname(__file__), "data")
MODEL_NAME = settings.OLLAMA_EMBEDDING_MODEL_NAME
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def main():
    print("🚀 Sentinel-Core 인덱싱 파이프라인 시작...")

    # --- 2. 데이터 폴더 확인 ---
    if not os.path.exists(DATA_PATH):
        os.makedirs(DATA_PATH)
        print(
            f"'{DATA_PATH}' 폴더를 생성했습니다. 인덱싱할 .md 또는 .txt 파일을 넣어주세요."
        )
        return

    # --- 3. 핵심 컴포넌트 초기화 ---
    print(f"데이터베이스 연결 중... ({DB_URL})")
    store = PGVectorStore(db_url=DB_URL)

    print(f"Ollama 임베딩 모델 로드 중... (모델: {MODEL_NAME})")
    # (Ollama가 실행 중이어야 합니다)
    embeddings = OllamaEmbeddings(model=MODEL_NAME)

    loader = DirectoryLoader(
        path=DATA_PATH,
        glob="**/*.md",
        show_progress=True,
        use_multithreading=True,
    )
    docs_md = loader.load()

    loader = DirectoryLoader(
        path=DATA_PATH,
        glob="**/*.txt",
        show_progress=True,
        use_multithreading=True,
    )
    docs_txt = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

    # --- 4. (Phase 1) 데이터 로드 ---
    print(f"\n[Phase 1/4] '{DATA_PATH}'에서 문서 로드 중...")
    docs = docs_md + docs_txt
    if not docs:
        print("로드할 문서가 없습니다. 파이프라인을 종료합니다.")
        return
    print(f"총 {len(docs)}개 문서 로드 완료.")

    # --- 5. (Phase 2) 문서 분할 (Split) ---
    print("[Phase 2/4] 문서를 청크로 분할 중...")
    chunks = text_splitter.split_documents(docs)
    print(f"총 {len(chunks)}개 청크 생성 완료.")

    # --- 6. (Phase 3) 임베딩 생성 (Embed) ---
    print(
        f"[Phase 3/4] {len(chunks)}개 청크 임베딩 생성 중... (시간이 걸릴 수 있습니다)"
    )
    chunk_texts = [chunk.page_content for chunk in chunks]

    # embed_documents는 List[List[float]]을 반환
    chunk_embeddings_list = embeddings.embed_documents(chunk_texts)

    # pgvector는 numpy 배열을 선호함
    chunk_embeddings_np = [np.array(emb) for emb in chunk_embeddings_list]
    print("임베딩 생성 완료.")

    # --- 7. (Phase 4) DB에 적재 (Load) ---
    print("[Phase 4/4] DB에 데이터 저장(Upsert) 중...")

    # PGVectorStore가 요구하는 형식(List[Dict])으로 변환
    docs_to_store: List[Dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        doc_id = chunk.metadata.get("source", f"unknown-source-{i}")

        # PGVectorStore의 upsert 메서드가 처리할 수 있도록 모든 정보를 담습니다.
        docs_to_store.append(
            {
                "doc_id": doc_id,
                "chunk_text": chunk.page_content,
                "embedding": chunk_embeddings_np[i],
                "metadata": chunk.metadata,
                # MVP: 모든 파일은 'file' 타입이고 'all_users'가 볼 수 있다고 가정
                "source_type": "file",
                "permission_groups": ["all_users"],
            }
        )

    # (중요) PGVectorStore의 `upsert_documents` 메서드가 이 데이터를
    # `documents`와 `document_chunks` 테이블에 나눠 저장해야 합니다.
    # *** 아래 [3단계: PGVectorStore 업데이트]를 꼭 보세요. ***
    try:
        store.upsert_documents(docs_to_store)
        print("\n✅ 인덱싱 파이프라인 성공적으로 완료!")
    except Exception as e:
        print(f"\n❌ 인덱싱 중 에러 발생: {e}")


if __name__ == "__main__":
    main()
