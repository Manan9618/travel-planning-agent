import pytest

from travel_agent.config import settings


@pytest.fixture(autouse=True)
def _dummy_openai_key(monkeypatch):
    """Ensure ChatOpenAI can be constructed offline; no real network calls happen in unit tests."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-dummy-key")


class FakeCache:
    """In-memory stand-in for Cache; avoids depending on a live Redis in unit tests."""

    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    @property
    def available(self) -> bool:
        return True

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value, ttl_seconds: int) -> None:
        self._store[key] = value


@pytest.fixture
def fake_cache() -> FakeCache:
    return FakeCache()
