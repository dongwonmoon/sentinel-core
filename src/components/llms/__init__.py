"""
대규모 언어 모델(LLM) 컴포넌트를 위한 패키지입니다.

이 패키지는 다음을 포함합니다:
- `base.py`: 모든 LLM 구현체가 상속해야 할 `BaseLLM` 추상 기반 클래스를 정의합니다.
- `ollama.py`: Ollama를 통해 로컬 언어 모델을 사용하는 LLM 구현체입니다.
- `openai.py`: OpenAI의 API(GPT-4, GPT-3.5 등)를 사용하는 LLM 구현체입니다.

새로운 LLM 제공자(예: Anthropic, Google Gemini)를 추가하려면,
`base.BaseLLM`을 상속받는 새로운 파일을 이 패키지 내에 생성하면 됩니다.
"""
