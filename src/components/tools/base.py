# -*- coding: utf-8 -*-
"""
에이전트가 사용할 수 있는 모든 '도구(Tool)'의 기본 인터페이스를 정의하는 모듈입니다.
"""

from langchain_core.tools import BaseTool as LangChainBaseTool

# LangChain의 BaseTool을 그대로 사용하여 타입 힌트 및 기본 클래스로 활용합니다.
# 우리 시스템의 모든 도구는 LangChain의 BaseTool 인터페이스를 따라야 합니다.
BaseTool = LangChainBaseTool
"""
우리 시스템에서 사용할 모든 도구의 기본 타입(Type)이자 기반 클래스(Base Class)입니다.

이 프로젝트에서는 LangChain의 `BaseTool` 클래스를 직접 별칭(alias)으로 사용합니다.
이는 다음과 같은 이점을 가집니다:
1.  **LangChain 생태계 호환성**: LangChain의 에이전트, 그래프(LangGraph) 등과
    별도의 변환 없이 완벽하게 호환됩니다.
2.  **표준화된 인터페이스**: 모든 도구가 일관된 구조를 갖도록 강제합니다.

`BaseTool`을 상속받는 모든 도구 클래스는 LLM(에이전트)이 해당 도구를 '이해'하고
'사용'할 수 있도록 다음과 같은 중요한 정보를 제공해야 합니다.

-   `name` (str):
    도구의 고유한 이름. LLM이 어떤 도구를 호출할지 식별하는 데 사용됩니다.
    (예: "web_search", "code_executor")

-   `description` (str):
    도구의 기능에 대한 상세한 설명. LLM은 이 설명을 읽고 사용자의 질문에 답하기 위해
    이 도구가 필요한지 여부를 판단합니다. 설명이 명확하고 상세할수록 LLM이 더 정확하게
    도구를 선택할 수 있습니다. (예: "최신 정보를 얻기 위해 웹을 검색합니다.")

-   `args_schema` (Pydantic BaseModel, 선택 사항):
    도구를 실행하는 데 필요한 인자(argument)들의 스키마. LLM은 이 스키마를 보고
    어떤 인자를, 어떤 형식으로 도구에 전달해야 하는지 파악합니다.
    (예: 웹 검색 도구는 'query'라는 문자열 인자가 필요함)

-   `_run` (동기) 또는 `_arun` (비동기) 메서드:
    도구의 실제 실행 로직. LLM이 도구 호출을 결정하면, 이 메서드가
    추출된 인자들과 함께 실행됩니다.
"""
