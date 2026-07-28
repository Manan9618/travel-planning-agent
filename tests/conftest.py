import pytest

from travel_agent.config import settings


@pytest.fixture(autouse=True)
def _dummy_openai_key(monkeypatch):
    """Ensure ChatOpenAI can be constructed offline; no real network calls happen in unit tests."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-dummy-key")
