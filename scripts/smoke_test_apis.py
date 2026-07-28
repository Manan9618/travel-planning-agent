#!/usr/bin/env python3
"""Week 1 deliverable: hello-world smoke tests for every external API.

Pings each configured API with a minimal, cheap request and reports pass/fail.
A missing key is reported as SKIPPED, not FAILED, so this is safe to run before
you've signed up for everything.

Usage:
    poetry run python scripts/smoke_test_apis.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import requests

sys.path.insert(0, "src")

from travel_agent.config import settings  # noqa: E402

TIMEOUT = 10


@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP"
    detail: str


def check_openai() -> CheckResult:
    if not settings.openai_api_key:
        return CheckResult("OpenAI", "SKIP", "OPENAI_API_KEY not set")
    try:
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            return CheckResult("OpenAI", "PASS", "listed models successfully")
        return CheckResult("OpenAI", "FAIL", f"HTTP {resp.status_code}: {resp.text[:200]}")
    except requests.RequestException as exc:
        return CheckResult("OpenAI", "FAIL", str(exc))


def check_amadeus() -> CheckResult:
    if not settings.amadeus_client_id or not settings.amadeus_client_secret:
        return CheckResult("Amadeus", "SKIP", "AMADEUS_CLIENT_ID/SECRET not set")
    try:
        token_resp = requests.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.amadeus_client_id,
                "client_secret": settings.amadeus_client_secret,
            },
            timeout=TIMEOUT,
        )
        if token_resp.status_code != 200:
            return CheckResult(
                "Amadeus", "FAIL", f"token HTTP {token_resp.status_code}: {token_resp.text[:200]}"
            )
        access_token = token_resp.json()["access_token"]
        search_resp = requests.get(
            "https://test.api.amadeus.com/v1/reference-data/locations",
            params={"keyword": "PAR", "subType": "CITY"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TIMEOUT,
        )
        if search_resp.status_code == 200:
            return CheckResult("Amadeus", "PASS", "authenticated and queried city search")
        return CheckResult(
            "Amadeus", "FAIL", f"search HTTP {search_resp.status_code}: {search_resp.text[:200]}"
        )
    except (requests.RequestException, KeyError) as exc:
        return CheckResult("Amadeus", "FAIL", str(exc))


def check_google_maps() -> CheckResult:
    if not settings.google_maps_api_key:
        return CheckResult("Google Maps", "SKIP", "GOOGLE_MAPS_API_KEY not set")
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": "Paris, France", "key": settings.google_maps_api_key},
            timeout=TIMEOUT,
        )
        body = resp.json()
        if resp.status_code == 200 and body.get("status") == "OK":
            return CheckResult("Google Maps", "PASS", "geocoded Paris, France")
        return CheckResult(
            "Google Maps", "FAIL", f"status={body.get('status')}: {body.get('error_message', '')}"
        )
    except requests.RequestException as exc:
        return CheckResult("Google Maps", "FAIL", str(exc))


def check_openweathermap() -> CheckResult:
    if not settings.openweathermap_api_key:
        return CheckResult("OpenWeatherMap", "SKIP", "OPENWEATHERMAP_API_KEY not set")
    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": "Paris", "appid": settings.openweathermap_api_key},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            return CheckResult("OpenWeatherMap", "PASS", "fetched current weather for Paris")
        return CheckResult("OpenWeatherMap", "FAIL", f"HTTP {resp.status_code}: {resp.text[:200]}")
    except requests.RequestException as exc:
        return CheckResult("OpenWeatherMap", "FAIL", str(exc))


def check_serper() -> CheckResult:
    if not settings.serper_api_key:
        return CheckResult("Serper", "SKIP", "SERPER_API_KEY not set")
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
            json={"q": "top attractions in Paris"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            return CheckResult("Serper", "PASS", "search query succeeded")
        return CheckResult("Serper", "FAIL", f"HTTP {resp.status_code}: {resp.text[:200]}")
    except requests.RequestException as exc:
        return CheckResult("Serper", "FAIL", str(exc))


def check_tavily() -> CheckResult:
    if not settings.tavily_api_key:
        return CheckResult("Tavily", "SKIP", "TAVILY_API_KEY not set")
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": settings.tavily_api_key, "query": "top attractions in Paris"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            return CheckResult("Tavily", "PASS", "search query succeeded")
        return CheckResult("Tavily", "FAIL", f"HTTP {resp.status_code}: {resp.text[:200]}")
    except requests.RequestException as exc:
        return CheckResult("Tavily", "FAIL", str(exc))


def main() -> int:
    checks = [
        check_openai,
        check_amadeus,
        check_google_maps,
        check_openweathermap,
        check_serper,
        check_tavily,
    ]
    results = [check() for check in checks]

    print(f"{'API':<16} {'STATUS':<6} DETAIL")
    print("-" * 70)
    for r in results:
        print(f"{r.name:<16} {r.status:<6} {r.detail}")

    failed = [r for r in results if r.status == "FAIL"]
    skipped = [r for r in results if r.status == "SKIP"]
    passed = [r for r in results if r.status == "PASS"]
    print("-" * 70)
    print(f"{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
