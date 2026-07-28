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
from datetime import date, timedelta

import requests

sys.path.insert(0, "src")

from travel_agent.config import settings  # noqa: E402

TIMEOUT = 10
BOOKING_RAPIDAPI_HOST = "booking-com15.p.rapidapi.com"


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


def check_travelpayouts() -> CheckResult:
    if not settings.travelpayouts_api_key:
        return CheckResult("TravelPayouts", "SKIP", "TRAVELPAYOUTS_API_KEY not set")
    try:
        resp = requests.get(
            "https://api.travelpayouts.com/v1/prices/cheap",
            params={"origin": "LON", "destination": "PAR", "token": settings.travelpayouts_api_key},
            timeout=TIMEOUT,
        )
        body = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if resp.status_code == 200 and body.get("success"):
            return CheckResult("TravelPayouts", "PASS", "fetched cheap fares LON->PAR")
        return CheckResult(
            "TravelPayouts", "FAIL", f"HTTP {resp.status_code}: {body or resp.text[:200]}"
        )
    except requests.RequestException as exc:
        return CheckResult("TravelPayouts", "FAIL", str(exc))


def check_booking_rapidapi() -> CheckResult:
    if not settings.booking_rapidapi_key:
        return CheckResult("Booking.com (RapidAPI)", "SKIP", "BOOKING_RAPIDAPI_KEY not set")
    headers = {
        "Content-Type": "application/json",
        "x-rapidapi-host": BOOKING_RAPIDAPI_HOST,
        "x-rapidapi-key": settings.booking_rapidapi_key,
    }
    try:
        dest_resp = requests.get(
            f"https://{BOOKING_RAPIDAPI_HOST}/api/v1/hotels/searchDestination",
            params={"query": "Paris"},
            headers=headers,
            timeout=TIMEOUT,
        )
        dest_body = dest_resp.json()
        if dest_resp.status_code != 200 or not dest_body.get("status"):
            return CheckResult(
                "Booking.com (RapidAPI)",
                "FAIL",
                f"destination HTTP {dest_resp.status_code}: {dest_body}",
            )
        city = next(
            (d for d in dest_body["data"] if d.get("dest_type") == "city"), dest_body["data"][0]
        )

        arrival = date.today() + timedelta(days=45)
        departure = arrival + timedelta(days=2)
        hotels_resp = requests.get(
            f"https://{BOOKING_RAPIDAPI_HOST}/api/v1/hotels/searchHotels",
            params={
                "dest_id": city["dest_id"],
                "search_type": city["search_type"].upper(),
                "adults": 1,
                "room_qty": 1,
                "page_number": 1,
                "units": "metric",
                "temperature_unit": "c",
                "languagecode": "en-us",
                "currency_code": "USD",
                "arrival_date": arrival.isoformat(),
                "departure_date": departure.isoformat(),
            },
            headers=headers,
            timeout=TIMEOUT,
        )
        hotels_body = hotels_resp.json()
        if hotels_resp.status_code == 200 and hotels_body.get("status"):
            n = len(hotels_body.get("data", {}).get("hotels", []))
            return CheckResult("Booking.com (RapidAPI)", "PASS", f"found {n} hotels in Paris")
        return CheckResult(
            "Booking.com (RapidAPI)",
            "FAIL",
            f"search HTTP {hotels_resp.status_code}: {hotels_body}",
        )
    except (requests.RequestException, KeyError, IndexError) as exc:
        return CheckResult("Booking.com (RapidAPI)", "FAIL", str(exc))


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
        check_travelpayouts,
        check_booking_rapidapi,
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
