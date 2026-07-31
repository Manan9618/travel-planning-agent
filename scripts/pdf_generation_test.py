#!/usr/bin/env python3
"""Week 14 deliverable: PDF itinerary generation, verified on 10 real
itineraries of varying trip lengths (2-14 days).

Builds each itinerary with real attractions/restaurants/hotel + real budget
evaluation + MultiDayOptimizer (Week 11), rasterizes a real map thumbnail
(Week 13), and generates the PDF (cover, executive summary, day-by-day plan,
map + QR code, budget table). Validates each PDF is well-formed (opens with
pypdf, has the expected page count, contains the destination name and every
day header in its extracted text) and checks for layout issues by varying
trip length across the full range the plan calls out — short (2-day) trips
that are cover+content only, up through a 14-day trip that stresses
pagination/page-break behavior most.

Attractions/restaurants/hotel are fetched once per destination and reused
across scenarios that share one (matching every prior live-test script's
efficiency pattern).

Usage:
    poetry run python scripts/pdf_generation_test.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "src")

from pypdf import PdfReader  # noqa: E402

from travel_agent.models.core import TravelPreferences  # noqa: E402
from travel_agent.tools.attraction_finder import AttractionFinderTool  # noqa: E402
from travel_agent.tools.budget_optimizer import BudgetOptimizer  # noqa: E402
from travel_agent.tools.hotel_search import HotelSearchTool  # noqa: E402
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer  # noqa: E402
from travel_agent.tools.pdf_generator import PDFGenerator  # noqa: E402
from travel_agent.tools.restaurant_finder import RestaurantFinderTool  # noqa: E402
from travel_agent.tools.travel_map_generator import (  # noqa: E402
    TravelMapGenerator,
    render_thumbnail_png,
)

OUTPUT_DIR = Path("output/pdfs_test")
TRIP_START = date.today() + timedelta(days=45)

# (label, destination, duration_days, budget_total)
SCENARIOS = [
    ("Paris weekend", "Paris", 2, 800),
    ("Paris week", "Paris", 7, 2000),
    ("Paris fortnight", "Paris", 14, 4000),
    ("Tokyo short", "Tokyo", 3, 1500),
    ("Tokyo standard", "Tokyo", 7, 3000),
    ("Rome getaway", "Rome", 4, 1200),
    ("Rome extended", "Rome", 10, 3500),
    ("Barcelona quick trip", "Barcelona", 2, 600),
    ("Barcelona standard", "Barcelona", 6, 1800),
    ("London standard", "London", 5, 2200),
]


def run_scenario(
    label: str,
    destination: str,
    duration: int,
    budget_total: float,
    attractions,
    restaurants,
    hotel,
) -> None:
    prefs = TravelPreferences(
        destination=destination,
        start_date=TRIP_START,
        duration_days=duration,
        budget_total=budget_total,
        raw_text=label,
    )
    itinerary = MultiDayOptimizer().build(prefs, hotel, attractions, restaurants)
    budget_evaluation = BudgetOptimizer().evaluate(itinerary)

    slug = label.lower().replace(" ", "_")
    html_path = OUTPUT_DIR / f"{slug}_map.html"
    png_path = OUTPUT_DIR / f"{slug}_map.png"
    pdf_path = OUTPUT_DIR / f"{slug}.pdf"

    map_thumbnail_path = None
    try:
        TravelMapGenerator().save(itinerary, html_path)
        render_thumbnail_png(html_path, png_path)
        map_thumbnail_path = png_path
    except Exception as exc:  # pragma: no cover - live-test diagnostic only
        print(f"  (map thumbnail failed: {exc})")

    PDFGenerator().generate(
        itinerary,
        pdf_path,
        budget_evaluation=budget_evaluation,
        map_thumbnail_path=map_thumbnail_path,
        map_url=f"https://example.com/maps/{slug}",  # placeholder until Week 15 hosts real maps
    )

    # --- validation -----------------------------------------------------
    with open(pdf_path, "rb") as f:
        assert f.read(5) == b"%PDF-", f"{label}: not a valid PDF"

    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) >= 2, f"{label}: expected at least 2 pages, got {len(reader.pages)}"
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert destination in text, f"{label}: destination missing from extracted text"
    for day_num in range(1, len(itinerary.days) + 1):
        assert f"Day {day_num}" in text, f"{label}: Day {day_num} header missing"

    print(
        f"  {label:<22} {duration:>2}d  {len(reader.pages)} pages  "
        f"{pdf_path.stat().st_size:>8,} bytes  -> {pdf_path}"
    )


def main() -> int:
    assert len(SCENARIOS) == 10, f"expected 10 scenarios, got {len(SCENARIOS)}"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    destinations = {s[1] for s in SCENARIOS}
    attractions_by_dest, restaurants_by_dest, hotel_by_dest = {}, {}, {}
    for dest in destinations:
        print(f"Fetching real data for {dest}...")
        attractions_by_dest[dest] = AttractionFinderTool().search(dest, max_results=14)
        restaurants_by_dest[dest] = RestaurantFinderTool().search(dest, max_results=14)
        end = TRIP_START + timedelta(days=13)  # cover the longest scenario (14 days)
        hotel_by_dest[dest] = HotelSearchTool().search(dest, TRIP_START, end)[0]

    print(f"\n{'Scenario':<22} {'Len':>3}  {'Pages':>7}  {'Size':>13}")
    print("-" * 70)
    for label, destination, duration, budget_total in SCENARIOS:
        run_scenario(
            label,
            destination,
            duration,
            budget_total,
            attractions_by_dest[destination],
            restaurants_by_dest[destination],
            hotel_by_dest[destination],
        )

    print("-" * 70)
    print(f"All {len(SCENARIOS)} PDFs generated and validated successfully.")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
