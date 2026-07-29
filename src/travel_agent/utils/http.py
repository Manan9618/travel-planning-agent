"""Shared HTTP helper: retries transient failures, treats other non-200s as empty."""

from __future__ import annotations

import logging

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class TransientError(Exception):
    """Raised for retryable failures (timeouts, connection errors, 429/5xx)."""


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(TransientError),
    reraise=True,
)
def get_json(
    url: str, params: dict | None = None, headers: dict | None = None, timeout: int = 10
) -> dict:
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise TransientError(str(exc)) from exc
    if _is_retryable_status(resp.status_code):
        raise TransientError(f"HTTP {resp.status_code}")
    if resp.status_code != 200:
        logger.warning(
            "Non-200 response from %s: HTTP %s: %s", url, resp.status_code, resp.text[:200]
        )
        return {}
    return resp.json()


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(TransientError),
    reraise=True,
)
def post_json(
    url: str, json_body: dict | None = None, headers: dict | None = None, timeout: int = 10
) -> dict:
    try:
        resp = requests.post(url, json=json_body, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise TransientError(str(exc)) from exc
    if _is_retryable_status(resp.status_code):
        raise TransientError(f"HTTP {resp.status_code}")
    if resp.status_code != 200:
        logger.warning(
            "Non-200 response from %s: HTTP %s: %s", url, resp.status_code, resp.text[:200]
        )
        return {}
    return resp.json()
