"""
에이전트가 사용할 수 있는 '도구(Tool)' 컴포넌트를 위한 패키지입니다.

도구는 에이전트가 LLM의 한계를 넘어 외부 세계와 상호작용하거나,
특정 작업을 수행할 수 있도록 하는 핵심적인 기능 단위입니다.

이 패키지는 다음을 포함합니다:
- `base.py`: 모든 도구 구현체가 상속해야 할 `BaseTool` 추상 기반 클래스를 정의합니다.
- `duckduckgo_search.py`: 웹 검색을 수행하는 DuckDuckGo 검색 도구입니다.
- `code_execution.py`: Python 코드를 안전한 환경에서 실행하는 도구입니다.
- `google_search.py`: (예시) Google 검색을 수행하는 도구입니다.

새로운 도구를 추가하려면, `base.BaseTool`을 상속받는 새로운 파일을
이 패키지 내에 생성하고, `core/factories.py`의 `get_tools` 함수에
해당 도구를 로드하는 로직을 추가하면 됩니다.
"""
