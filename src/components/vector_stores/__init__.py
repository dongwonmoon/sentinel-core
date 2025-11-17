"""
벡터 저장소(Vector Store) 컴포넌트를 위한 패키지입니다.

벡터 저장소는 텍스트의 임베딩(벡터)을 저장, 인덱싱하고, 주어진 쿼리 벡터와
유사한 벡터들을 효율적으로 검색하는 역할을 하는 특수한 데이터베이스입니다.
RAG(Retrieval-Augmented Generation) 파이프라인의 핵심적인 구성 요소입니다.

이 패키지는 다음을 포함합니다:
- `base.py`: 모든 벡터 저장소 구현체가 상속해야 할 `BaseVectorStore` 추상 기반 클래스를 정의합니다.
- `pg_vector_store.py`: PostgreSQL 데이터베이스와 `pgvector` 확장을 사용하는 벡터 저장소 구현체입니다.
- `milvus_vector_store.py`: 오픈 소스 벡터 데이터베이스인 Milvus를 사용하는 벡터 저장소 구현체입니다.

새로운 벡터 저장소 제공자(예: ChromaDB, Pinecone)를 추가하려면,
`base.BaseVectorStore`를 상속받는 새로운 파일을 이 패키지 내에 생성하면 됩니다.
"""
