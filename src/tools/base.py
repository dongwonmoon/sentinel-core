# tools/base.py
from langchain_core.tools import BaseTool as LangChainBaseTool

# LangChain의 BaseTool을 그대로 사용하여 타입 힌트로 활용합니다.
# 우리 시스템의 모든 도구는 LangChain의 BaseTool 인터페이스를 따라야 합니다.
BaseTool = LangChainBaseTool
"""
우리 시스템에서 사용할 모든 도구의 기본 타입입니다.
LangChain의 BaseTool 클래스를 별칭으로 사용하며,
모든 도구는 'name', 'description', '_run' 또는 '_arun' 메서드를
구현해야 함을 명시합니다.
"""
