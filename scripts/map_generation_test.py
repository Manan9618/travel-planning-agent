#!/usr/bin/env python3
"""Week 13 deliverable: interactive map generation, verified against real
built itineraries.

Builds a real itinerary (real attractions/restaurants/hotel + MultiDayOptimizer,
Week 11) for each sample trip, renders it with TravelMapGenerator (hotel pin +
day-colored stop pins + per-day route polylines + a day-by-day reveal
timeline), saves the self-contained HTML map, and rasterizes a PNG thumbnail
via headless Chromium (Playwright) — the same static image Week 14's PDF
generator will embed. Output under output/maps/ (gitignored — generated
artifacts, not source) for visual inspection.

Usage:
    poetry run python scripts/map_generation_test.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "src")

from travel_agent.models.core import TravelPreferences  # noqa: E402
from travel_agent.tools.attraction_finder import AttractionFinderTool  # noqa: E402
from travel_agent.tools.hotel_search import HotelSearchTool  # noqa: E402
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer  # noqa: E402
from travel_agent.tools.restaurant_finder import RestaurantFinderTool  # noqa: E402
from travel_agent.tools.travel_map_generator import (  # noqa: E402
    TravelMapGenerator,
    render_thumbnail_png,
)

OUTPUT_DIR = Path("output/maps")
TRIP_START = date.today() + timedelta(days=45)

CITIES = ["Paris", "Tokyo"]


def run_city(city: str) -> None:
    print(f"\n{'=' * 70}\n{city}\n{'=' * 70}")
    attractions = AttractionFinderTool().search(city, max_results=12)
    restaurants = RestaurantFinderTool().search(city, max_results=12)
    hotel = HotelSearchTool().search(city, TRIP_START, TRIP_START + timedelta(days=6))[0]

    prefs = TravelPreferences(
        destination=city,
        start_date=TRIP_START,
        duration_days=6,
        raw_text=f"6-day trip to {city}",
    )
    itinerary = MultiDayOptimizer().build(prefs, hotel, attractions, restaurants)

    slug = city.lower().replace(" ", "_")
    html_path = OUTPUT_DIR / f"{slug}.html"
    png_path = OUTPUT_DIR / f"{slug}_thumbnail.png"

    generator = TravelMapGenerator()
    generator.save(itinerary, html_path)
    render_thumbnail_png(html_path, png_path)

    stops = sum(1 for d in itinerary.days for i in d.items if i.lat is not None)
    print(f"{len(itinerary.days)} days, {stops} mapped stops")
    print(f"Wrote {html_path} ({html_path.stat().st_size:,} bytes)")
    print(f"Wrote {png_path} ({png_path.stat().st_size:,} bytes)")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for city in CITIES:
        run_city(city)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
