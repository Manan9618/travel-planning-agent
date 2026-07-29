"""Redis-backed response cache. Degrades to a safe no-op if Redis is unreachable.

Used by search tools (Week 2+) to avoid re-hitting rate-limited external APIs.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis

from travel_agent.config import settings

logger = logging.getLogger(__name__)


class Cache:
    def __init__(self, url: str | None = None) -> None:
        self._client: redis.Redis | None = None
        try:
            client = redis.Redis.from_url(
                url or settings.redis_url, socket_connect_timeout=1, socket_timeout=1
            )
            client.ping()
            self._client = client
        except redis.RedisError as exc:
            logger.warning("Redis unavailable (%s); caching disabled for this run", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    def get(self, key: str) -> Any | None:
        if self._client is None:
            return None
        try:
            raw = self._client.get(key)
        except redis.RedisError as exc:
            logger.warning("Redis GET failed for %s: %s", key, exc)
            return None
        return json.loads(raw) if raw else None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self._client is None:
            return
        try:
            self._client.set(key, json.dumps(value), ex=ttl_seconds)
        except redis.RedisError as exc:
            logger.warning("Redis SET failed for %s: %s", key, exc)
