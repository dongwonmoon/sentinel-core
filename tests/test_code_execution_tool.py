import pytest

from src.components.tools.code_execution import SafePythonREPLTool


def test_code_execution_success():
    tool = SafePythonREPLTool()
    output = tool._run("print(1 + 2)")
    assert output == "3"


def test_code_execution_rejects_banned_pattern():
    tool = SafePythonREPLTool()
    with pytest.raises(ValueError):
        tool._run("import os\nprint('hi')")


def test_code_execution_length_guard():
    tool = SafePythonREPLTool()
    long_code = "print('x')\n" * 3000
    with pytest.raises(ValueError):
        tool._run(long_code)
