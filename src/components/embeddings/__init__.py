"""
텍스트 임베딩 모델 컴포넌트를 위한 패키지입니다.

이 패키지는 다음을 포함합니다:
- `base.py`: 모든 임베딩 모델 구현체가 상속해야 할 `BaseEmbeddingModel` 추상 기반 클래스를 정의합니다.
- `ollama.py`: Ollama를 통해 로컬 언어 모델을 사용하는 임베딩 모델 구현체입니다.
- `openai.py`: OpenAI의 API를 사용하는 임베딩 모델 구현체입니다.

새로운 임베딩 모델 제공자(예: Cohere, HuggingFace)를 추가하려면,
`base.BaseEmbeddingModel`을 상속받는 새로운 파일을 이 패키지 내에 생성하면 됩니다.
"""
