"""
검색 결과 재순위(Reranking) 모델 컴포넌트를 위한 패키지입니다.

리랭커는 RAG(Retrieval-Augmented Generation) 파이프라인에서 초기 검색(retrieval)된
문서 목록의 순서를 사용자의 쿼리와의 의미적 관련성을 기준으로 다시 정렬하여,
최종적으로 LLM에 전달될 컨텍스트의 품질을 향상시키는 역할을 합니다.

이 패키지는 다음을 포함합니다:
- `base.py`: 모든 리랭커 구현체가 상속해야 할 `BaseReranker` 추상 기반 클래스를 정의합니다.
- `noop_reranker.py`: 아무 작업도 하지 않는 'No-Operation' 리랭커 구현체입니다.
  리랭킹을 사용하지 않을 경우에 사용됩니다.

새로운 리랭커 제공자(예: Cohere, Cross-Encoder)를 추가하려면,
`base.BaseReranker`를 상속받는 새로운 파일을 이 패키지 내에 생성하면 됩니다.
"""
