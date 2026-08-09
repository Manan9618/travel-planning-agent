"""SemanticCache — Week 20 deliverable.

`Cache` (exact-key) misses on paraphrases: "5 days in Paris under $3000" and
"a five-day Paris trip, $3000 budget" mean the same thing to `PreferenceParser`
but hash to different keys, so each pays a full LLM call. This catches those
near-duplicates via cosine similarity over OpenAI embeddings instead of an exact
string match.

Entries are stored as a single bounded JSON list per namespace in Redis, not as
one Redis key per entry — there's no index to maintain, just a linear scan over
at most `max_entries` vectors, which is simple, correct, and fast enough for a
cache that serves one hot path a few times a second. A real vector index (e.g.
GPTCache + a dedicated vector DB) would be infrastructure this project doesn't
otherwise need, for a workload this small.

A similarity match alone isn't safe for callers whose output depends on exact
values embeddings don't reliably distinguish (a budget of $1000 vs $5000, or a
date resolved against "today"). `guard` exists for that: two texts only count as
a match if their embeddings are similar *and* their guards are identical, so a
caller can require (for example) matching digit tokens and a matching reference
date before ever reusing a cached result — see `PreferenceParser._cache_guard`.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from travel_agent.utils.cache import Cache

logger = logging.getLogger(__name__)

# Calibrated against real text-embedding-3-small output (Week 20 live
# testing), not a guess: two independently-worded descriptions of the SAME
# trip ("5 days in Paris under $3000 starting July 2026" vs "Paris trip for
# 5 days, budget $3000, starting July 2026") scored ~0.82 cosine similarity
# - nowhere near the ~0.97+ a naive reading of "cosine similarity" might
# suggest for "obviously the same thing". A DIFFERENT destination with the
# same numbers scored ~0.78, uncomfortably close to that 0.82. Whole-text
# embedding similarity alone can't reliably separate those two cases at any
# single threshold - see `PreferenceParser._cache_guard`, which is the
# actual line of defense against a wrong-destination or wrong-budget false
# match; this threshold's job is only to reject completely unrelated text
# (measured ~0.47 for two genuinely different requests), which it does with
# a wide margin.
DEFAULT_SIMILARITY_THRESHOLD = 0.80
DEFAULT_TTL_SECONDS = 24 * 3600
DEFAULT_MAX_ENTRIES = 200


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticCache:
    def __init__(
        self,
        namespace: str,
        embed: Callable[[str], list[float]],
        cache: Cache | None = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._key = f"semantic_cache:{namespace}"
        self._embed = embed
        self._cache = cache or Cache()
        self._threshold = similarity_threshold
        self._ttl = ttl_seconds
        self._max_entries = max_entries

    def get(self, text: str, guard: str = "") -> Any | None:
        entries = self._cache.get(self._key) or []
        candidates = [e for e in entries if e.get("guard") == guard]
        if not candidates:
            return None

        query_vec = self._embed(text)
        best_entry, best_score = None, 0.0
        for entry in candidates:
            score = _cosine_similarity(query_vec, entry["embedding"])
            if score > best_score:
                best_entry, best_score = entry, score

        if best_entry is not None and best_score >= self._threshold:
            logger.info("Semantic cache hit (namespace=%s, score=%.4f)", self._key, best_score)
            return best_entry["value"]
        return None

    def set(self, text: str, value: Any, guard: str = "") -> None:
        entries = self._cache.get(self._key) or []
        entries.append(
            {"text": text, "embedding": self._embed(text), "value": value, "guard": guard}
        )
        entries = entries[-self._max_entries :]
        self._cache.set(self._key, entries, self._ttl)
