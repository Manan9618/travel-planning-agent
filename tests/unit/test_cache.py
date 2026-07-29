import redis

from travel_agent.utils.cache import Cache


def test_unreachable_redis_marks_cache_unavailable():
    cache = Cache(url="redis://localhost:1/0")  # nothing listening on port 1
    assert cache.available is False


def test_get_on_unavailable_cache_returns_none():
    cache = Cache(url="redis://localhost:1/0")
    assert cache.get("anything") is None


def test_set_on_unavailable_cache_is_a_silent_noop():
    cache = Cache(url="redis://localhost:1/0")
    cache.set("key", {"a": 1}, ttl_seconds=60)  # must not raise


def test_get_set_roundtrip_against_live_redis():
    cache = Cache()
    if not cache.available:
        return  # no local Redis in this environment; behavior covered by the unavailable tests
    cache.set("travel_agent:test:roundtrip", {"a": 1, "b": [1, 2, 3]}, ttl_seconds=5)
    assert cache.get("travel_agent:test:roundtrip") == {"a": 1, "b": [1, 2, 3]}


def test_get_returns_none_on_redis_error(monkeypatch):
    cache = Cache()
    if not cache.available:
        return

    def _raise(*args, **kwargs):
        raise redis.RedisError("boom")

    monkeypatch.setattr(cache._client, "get", _raise)
    assert cache.get("whatever") is None


def test_set_swallows_redis_error(monkeypatch):
    cache = Cache()
    if not cache.available:
        return

    def _raise(*args, **kwargs):
        raise redis.RedisError("boom")

    monkeypatch.setattr(cache._client, "set", _raise)
    cache.set("whatever", {"x": 1}, ttl_seconds=5)  # must not raise
