import pytest
from unittest.mock import MagicMock
from pydantic_ai import Agent

def pytest_addoption(parser):
    parser.addoption(
        "--llm", action="store_true", default=False, help="run tests with real LLM"
    )

@pytest.fixture
def llm_agent(request):
    use_real_llm = request.config.getoption("--llm")
    if use_real_llm:
        # Ensure you have the necessary API keys set up in your environment
        # for this to work.
        return Agent(model="openai:gpt-4o")
    else:
        mock_llm = MagicMock()
        mock_llm.run.return_value = "This is a red square."
        return Agent(llm=mock_llm)
