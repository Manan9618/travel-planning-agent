from travel_agent.utils.semantic_cache import SemanticCache

# Simple 2D vectors under the caller's control instead of real embeddings -
# cosine similarity between (1, 0) and (1, 0) is 1.0 (identical), between
# (1, 0) and (0.99, 0.14) is ~0.99 (near-duplicate phrasing), and between
# (1, 0) and (0, 1) is 0.0 (unrelated) - enough range to exercise the
# threshold without depending on a real embedding model in a unit test.
_VECTORS = {
    "paris trip": [1.0, 0.0],
    "paris trip paraphrase": [0.99, 0.1411],  # cos sim ~0.99 with "paris trip"
    "tokyo trip": [0.0, 1.0],  # orthogonal - cos sim 0.0
}


def _embed(text: str) -> list[float]:
    return _VECTORS[text]


def _semantic_cache(fake_cache, **kwargs) -> SemanticCache:
    return SemanticCache("test", embed=_embed, cache=fake_cache, **kwargs)


def test_get_on_empty_cache_returns_none(fake_cache):
    cache = _semantic_cache(fake_cache)
    assert cache.get("paris trip") is None


def test_identical_text_is_a_hit(fake_cache):
    cache = _semantic_cache(fake_cache)
    cache.set("paris trip", {"destination": "Paris"})
    assert cache.get("paris trip") == {"destination": "Paris"}


def test_near_duplicate_phrasing_above_threshold_is_a_hit(fake_cache):
    cache = _semantic_cache(fake_cache, similarity_threshold=0.97)
    cache.set("paris trip", {"destination": "Paris"})
    assert cache.get("paris trip paraphrase") == {"destination": "Paris"}


def test_unrelated_text_below_threshold_is_a_miss(fake_cache):
    cache = _semantic_cache(fake_cache, similarity_threshold=0.97)
    cache.set("paris trip", {"destination": "Paris"})
    assert cache.get("tokyo trip") is None


def test_guard_mismatch_blocks_an_otherwise_identical_hit(fake_cache):
    """The whole reason `guard` exists: a caller (e.g. PreferenceParser) can
    require exact agreement on values embeddings won't reliably distinguish
    (a budget number, a reference date) before ever trusting a similarity
    match."""
    cache = _semantic_cache(fake_cache)
    cache.set("paris trip", {"budget": 3000}, guard="2026-01-01:3000")
    assert cache.get("paris trip", guard="2026-01-01:1000") is None


def test_guard_match_allows_the_hit(fake_cache):
    cache = _semantic_cache(fake_cache)
    cache.set("paris trip", {"budget": 3000}, guard="2026-01-01:3000")
    assert cache.get("paris trip", guard="2026-01-01:3000") == {"budget": 3000}


def test_max_entries_evicts_oldest(fake_cache):
    cache = _semantic_cache(fake_cache, max_entries=2)
    cache.set("paris trip", {"n": 1})
    cache.set("tokyo trip", {"n": 2})
    cache.set("paris trip paraphrase", {"n": 3})  # evicts "paris trip" (oldest)

    entries = fake_cache.get("semantic_cache:test")
    assert len(entries) == 2
    assert {e["text"] for e in entries} == {"tokyo trip", "paris trip paraphrase"}


def test_set_persists_with_the_given_ttl(fake_cache, monkeypatch):
    recorded = {}
    original_set = fake_cache.set

    def _spy_set(key, value, ttl_seconds):
        recorded["ttl_seconds"] = ttl_seconds
        original_set(key, value, ttl_seconds)

    monkeypatch.setattr(fake_cache, "set", _spy_set)
    cache = _semantic_cache(fake_cache, ttl_seconds=123)
    cache.set("paris trip", {"n": 1})
    assert recorded["ttl_seconds"] == 123
