"""
애플리케이션의 핵심 에이전트 로직을 구성하는 패키지입니다.

이 패키지는 LangGraph를 사용하여 정의된 에이전트의 상태(State), 노드(Node),
그리고 그래프(Graph) 자체를 포함합니다.

- `state.py`: 에이전트의 상태(`AgentState`)를 정의합니다.
- `nodes.py`: 그래프의 각 노드에서 실행될 실제 로직을 포함합니다.
- `graph.py`: 노드들을 연결하여 전체 실행 흐름(워크플로우)을 정의하는 그래프를 생성합니다.

`__init__.py`에서는 `orchestrator.py`의 `Orchestrator` 클래스를 `Agent`라는 이름으로
외부에 노출합니다. 이는 내부적으로 복잡한 오케스트레이션 로직을 'Agent'라는
더 단순하고 추상적인 이름으로 감싸, 다른 모듈에서 쉽게 사용할 수 있도록 하기 위함입니다.
"""

from ..orchestrator import Orchestrator as Agent

__all__ = ["Agent"]
