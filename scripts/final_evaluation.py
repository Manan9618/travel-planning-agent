#!/usr/bin/env python3
"""Week 22 deliverable: final evaluation, 30 scenarios, compared against the
Week 12 baseline (`scripts/agent_evaluation.py`, 25 scenarios, 5.52/10 average).

Reuses the exact same rubric/machinery as Week 12 (`ItineraryEvaluator` — 6
computed dimensions + 4 LLM-judged via `ItineraryJudge`) rather than inventing
a new one, so the two runs are genuinely comparable. Extends Week 12's 25
scenarios with 5 more covering the 2 TripStyles the plan names but Week 12
never actually exercised (`business`, `road_trip`) plus 5 new destinations,
for real coverage growth rather than padding the count.

Run twice around a fix — once before, once after — with `--tag` to keep the
outputs separate:
    poetry run python scripts/final_evaluation.py --tag before
    poetry run python scripts/final_evaluation.py --tag after

Outputs:
    output/evaluation/final_{tag}_results.csv
    output/evaluation/final_{tag}_report.html

Usage:
    poetry run python scripts/final_evaluation.py [--tag TAG]
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "src")

from travel_agent.models.core import BudgetTier, Pace, TravelPreferences, TripStyle  # noqa: E402
from travel_agent.tools.attraction_finder import AttractionFinderTool  # noqa: E402
from travel_agent.tools.evaluator import ItineraryEvaluator  # noqa: E402
from travel_agent.tools.hotel_search import HotelSearchTool  # noqa: E402
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer  # noqa: E402
from travel_agent.tools.restaurant_finder import RestaurantFinderTool  # noqa: E402
from travel_agent.tools.weather_checker import WeatherCheckerTool  # noqa: E402

OUTPUT_DIR = Path("output/evaluation")
FAR_START = date.today() + timedelta(days=45)
NEAR_START = date.today() + timedelta(days=2)  # inside OpenWeatherMap's free-tier horizon

DIMENSION_NAMES = [
    "feasibility",
    "budget_accuracy",
    "geo_efficiency",
    "weather_match",
    "completeness",
    "variety",
    "personalization_fit",
    "narrative_quality",
    "practicality",
    "overall_satisfaction",
]

# Week 12's original 25 scenarios, unchanged (see scripts/agent_evaluation.py
# for the per-scenario rationale) plus 5 new ones below covering the 2
# TripStyles the plan names but Week 12 never used (business, road_trip) and
# 5 destinations not seen in any prior live-test script in this project.
SCENARIOS = [
    (
        "Paris city break",
        "Paris",
        TripStyle.CITY,
        5,
        1800,
        BudgetTier.MID_RANGE,
        Pace.MODERATE,
        ["art", "history"],
        ["Louvre"],
        NEAR_START,
    ),
    (
        "Paris honeymoon",
        "Paris",
        TripStyle.HONEYMOON,
        5,
        4500,
        BudgetTier.LUXURY,
        Pace.RELAXED,
        ["romance", "food"],
        [],
        FAR_START,
    ),
    (
        "London city break",
        "London",
        TripStyle.CITY,
        6,
        2200,
        BudgetTier.MID_RANGE,
        Pace.MODERATE,
        ["museums"],
        ["Tower"],
        FAR_START,
    ),
    (
        "London family trip",
        "London",
        TripStyle.FAMILY,
        6,
        3000,
        BudgetTier.MID_RANGE,
        Pace.RELAXED,
        ["family-friendly"],
        [],
        FAR_START,
    ),
    (
        "Tokyo city break",
        "Tokyo",
        TripStyle.CITY,
        7,
        2800,
        BudgetTier.MID_RANGE,
        Pace.PACKED,
        ["food", "technology"],
        ["Shibuya"],
        FAR_START,
    ),
    (
        "Tokyo solo trip",
        "Tokyo",
        TripStyle.SOLO,
        5,
        1500,
        BudgetTier.BACKPACKER,
        Pace.MODERATE,
        ["culture"],
        [],
        FAR_START,
    ),
    (
        "Rome city break",
        "Rome",
        TripStyle.CITY,
        5,
        1800,
        BudgetTier.MID_RANGE,
        Pace.MODERATE,
        ["history"],
        ["Colosseum"],
        FAR_START,
    ),
    (
        "Rome honeymoon",
        "Rome",
        TripStyle.HONEYMOON,
        5,
        4000,
        BudgetTier.LUXURY,
        Pace.RELAXED,
        ["romance"],
        [],
        FAR_START,
    ),
    (
        "Barcelona city break",
        "Barcelona",
        TripStyle.CITY,
        5,
        1600,
        BudgetTier.MID_RANGE,
        Pace.MODERATE,
        ["architecture"],
        ["Sagrada"],
        FAR_START,
    ),
    (
        "Barcelona beach trip",
        "Barcelona",
        TripStyle.BEACH,
        6,
        2000,
        BudgetTier.MID_RANGE,
        Pace.RELAXED,
        ["beach", "nightlife"],
        [],
        FAR_START,
    ),
    (
        "New York city break",
        "New York",
        TripStyle.CITY,
        6,
        2500,
        BudgetTier.MID_RANGE,
        Pace.PACKED,
        ["shopping"],
        [],
        FAR_START,
    ),
    (
        "New York solo trip",
        "New York",
        TripStyle.SOLO,
        4,
        1200,
        BudgetTier.BACKPACKER,
        Pace.MODERATE,
        ["art"],
        [],
        FAR_START,
    ),
    (
        "Bali beach trip",
        "Bali",
        TripStyle.BEACH,
        7,
        1800,
        BudgetTier.BACKPACKER,
        Pace.RELAXED,
        ["beach", "wellness"],
        [],
        NEAR_START,
    ),
    (
        "Bali honeymoon",
        "Bali",
        TripStyle.HONEYMOON,
        7,
        5000,
        BudgetTier.LUXURY,
        Pace.RELAXED,
        ["romance", "spa"],
        [],
        FAR_START,
    ),
    (
        "Bangkok solo trip",
        "Bangkok",
        TripStyle.SOLO,
        5,
        900,
        BudgetTier.BACKPACKER,
        Pace.MODERATE,
        ["street food"],
        [],
        FAR_START,
    ),
    (
        "Bangkok adventure trip",
        "Bangkok",
        TripStyle.ADVENTURE,
        6,
        1400,
        BudgetTier.BACKPACKER,
        Pace.PACKED,
        ["adventure"],
        [],
        FAR_START,
    ),
    (
        "Reykjavik adventure trip",
        "Reykjavik",
        TripStyle.ADVENTURE,
        5,
        3000,
        BudgetTier.MID_RANGE,
        Pace.PACKED,
        ["nature", "hiking"],
        [],
        FAR_START,
    ),
    (
        "Reykjavik honeymoon",
        "Reykjavik",
        TripStyle.HONEYMOON,
        5,
        4500,
        BudgetTier.LUXURY,
        Pace.RELAXED,
        ["northern lights"],
        [],
        FAR_START,
    ),
    (
        "Orlando family trip",
        "Orlando",
        TripStyle.FAMILY,
        6,
        3500,
        BudgetTier.MID_RANGE,
        Pace.PACKED,
        ["theme parks"],
        [],
        FAR_START,
    ),
    (
        "Orlando adventure trip",
        "Orlando",
        TripStyle.ADVENTURE,
        5,
        2200,
        BudgetTier.MID_RANGE,
        Pace.PACKED,
        ["theme parks", "adventure"],
        [],
        FAR_START,
    ),
    (
        "Lisbon solo trip",
        "Lisbon",
        TripStyle.SOLO,
        5,
        1100,
        BudgetTier.BACKPACKER,
        Pace.MODERATE,
        ["food", "culture"],
        [],
        FAR_START,
    ),
    (
        "Lisbon city break",
        "Lisbon",
        TripStyle.CITY,
        5,
        1600,
        BudgetTier.MID_RANGE,
        Pace.MODERATE,
        ["history"],
        [],
        FAR_START,
    ),
    (
        "Prague solo trip",
        "Prague",
        TripStyle.SOLO,
        4,
        900,
        BudgetTier.BACKPACKER,
        Pace.MODERATE,
        ["architecture", "nightlife"],
        [],
        FAR_START,
    ),
    (
        "Santorini beach trip",
        "Santorini",
        TripStyle.BEACH,
        5,
        2500,
        BudgetTier.MID_RANGE,
        Pace.RELAXED,
        ["beach", "views"],
        [],
        FAR_START,
    ),
    (
        "Santorini honeymoon",
        "Santorini",
        TripStyle.HONEYMOON,
        5,
        5000,
        BudgetTier.LUXURY,
        Pace.RELAXED,
        ["romance", "views"],
        [],
        FAR_START,
    ),
    # --- 5 new for Week 22: 2 previously-unexercised TripStyles + 5 new destinations ---
    (
        "Sydney business trip",
        "Sydney",
        TripStyle.BUSINESS,
        4,
        3500,
        BudgetTier.MID_RANGE,
        Pace.PACKED,
        ["business", "networking"],
        [],
        FAR_START,
    ),
    (
        "Cape Town adventure trip",
        "Cape Town",
        TripStyle.ADVENTURE,
        7,
        2400,
        BudgetTier.MID_RANGE,
        Pace.PACKED,
        ["safari", "hiking"],
        [],
        FAR_START,
    ),
    (
        "Dubai honeymoon",
        "Dubai",
        TripStyle.HONEYMOON,
        5,
        6000,
        BudgetTier.LUXURY,
        Pace.RELAXED,
        ["luxury", "shopping"],
        [],
        FAR_START,
    ),
    (
        "Las Vegas road trip",
        "Las Vegas",
        TripStyle.ROAD_TRIP,
        6,
        2000,
        BudgetTier.MID_RANGE,
        Pace.PACKED,
        ["nightlife", "nature"],
        [],
        FAR_START,
    ),
    (
        "Vienna solo trip",
        "Vienna",
        TripStyle.SOLO,
        4,
        1000,
        BudgetTier.BACKPACKER,
        Pace.MODERATE,
        ["music", "history"],
        [],
        NEAR_START,
    ),
]


def _fetch_destination_data(
    destinations: set[str], dest_tier_pairs: set[tuple[str, BudgetTier]]
) -> tuple[dict, dict, dict]:
    attractions_by_dest, restaurants_by_dest, hotel_by_dest_tier = {}, {}, {}
    for dest in destinations:
        print(f"Fetching real data for {dest}...")
        attractions_by_dest[dest] = AttractionFinderTool().search(dest, max_results=14)
        restaurants_by_dest[dest] = RestaurantFinderTool().search(dest, max_results=14)

    end = FAR_START + timedelta(days=6)
    # Keyed by (destination, budget_tier), not just destination: several
    # destinations host scenarios at more than one tier (e.g. Paris city
    # break at MID_RANGE, Paris honeymoon at LUXURY) - a single
    # tier-unaware fetch per destination would silently reuse one tier's
    # mock hotel price for every tier at that destination, defeating the
    # Week 22 budget_accuracy fix below.
    for dest, tier in dest_tier_pairs:
        hotel_by_dest_tier[(dest, tier)] = HotelSearchTool().search(
            dest, FAR_START, end, budget_tier=tier
        )[0]
    return attractions_by_dest, restaurants_by_dest, hotel_by_dest_tier


def _write_csv(rows: list[dict], tag: str) -> Path:
    path = OUTPUT_DIR / f"final_{tag}_results.csv"
    fieldnames = ["scenario", "destination", "trip_style", "overall_score", *DIMENSION_NAMES]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_html(rows: list[dict], failure_modes: list[tuple[str, float]], tag: str) -> Path:
    path = OUTPUT_DIR / f"final_{tag}_report.html"
    header_cells = "".join(f"<th>{d}</th>" for d in DIMENSION_NAMES)
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{row[d]:.1f}</td>" if row[d] is not None else "<td>n/a</td>"
            for d in DIMENSION_NAMES
        )
        body_rows.append(
            f"<tr><td>{row['scenario']}</td><td>{row['trip_style']}</td>"
            f"<td>{row['overall_score']:.1f}</td>{cells}</tr>"
        )
    failure_rows = "".join(
        f"<li><b>{name}</b> — average {avg:.1f}/10</li>" for name, avg in failure_modes
    )
    avg_overall = sum(r["overall_score"] for r in rows) / len(rows)
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Final Evaluation Report ({tag}) — Week 22</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
th, td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: right; }}
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
th {{ background: #f0f0f0; }}
</style></head>
<body>
<h1>Final Evaluation Report ({tag}) — Week 22</h1>
<p>{len(rows)} scenarios evaluated. Average overall score: <b>{avg_overall:.2f}/10</b></p>
<h2>Top failure modes (lowest-average dimensions)</h2>
<ul>{failure_rows}</ul>
<h2>Full results</h2>
<table>
<tr><th>Scenario</th><th>Style</th><th>Overall</th>{header_cells}</tr>
{"".join(body_rows)}
</table>
</body></html>
"""
    path.write_text(html)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tag", default="run", help="Distinguishes output files, e.g. before/after"
    )
    args = parser.parse_args()

    assert len(SCENARIOS) == 30, f"expected 30 scenarios, got {len(SCENARIOS)}"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    destinations = {s[1] for s in SCENARIOS}
    dest_tier_pairs = {(s[1], s[5]) for s in SCENARIOS}
    attractions_by_dest, restaurants_by_dest, hotel_by_dest_tier = _fetch_destination_data(
        destinations, dest_tier_pairs
    )

    optimizer = MultiDayOptimizer()
    evaluator = ItineraryEvaluator()
    weather_tool = WeatherCheckerTool()

    rows = []
    for label, dest, style, duration, budget, tier, pace, interests, must_see, start in SCENARIOS:
        prefs = TravelPreferences(
            destination=dest,
            start_date=start,
            duration_days=duration,
            budget_total=budget,
            budget_tier=tier,
            trip_style=style,
            pace=pace,
            interests=interests,
            must_see=must_see,
            raw_text=label,
        )
        end = start + timedelta(days=duration - 1)
        weather = weather_tool.get_forecast(dest, start, end)

        itinerary = optimizer.build(
            prefs,
            hotel_by_dest_tier[(dest, tier)],
            attractions_by_dest[dest],
            restaurants_by_dest[dest],
            weather=weather,
        )
        report = evaluator.evaluate(itinerary, scenario_label=label)
        scores = report.scores_by_name
        row = {
            "scenario": label,
            "destination": dest,
            "trip_style": style.value,
            "overall_score": report.overall_score,
            **{d: scores.get(d) for d in DIMENSION_NAMES},
        }
        rows.append(row)
        print(f"  {label:<28} overall={report.overall_score:.1f}")

    dimension_averages = []
    for dim in DIMENSION_NAMES:
        values = [r[dim] for r in rows if r[dim] is not None]
        if values:
            dimension_averages.append((dim, sum(values) / len(values)))
    failure_modes = sorted(dimension_averages, key=lambda kv: kv[1])[:5]

    csv_path = _write_csv(rows, args.tag)
    html_path = _write_html(rows, failure_modes, args.tag)

    avg_overall = sum(r["overall_score"] for r in rows) / len(rows)
    print("\n" + "-" * 60)
    print(f"[{args.tag}] Average overall score: {avg_overall:.2f}/10")
    print(f"\n[{args.tag}] All dimension averages:")
    for name, avg in sorted(dimension_averages, key=lambda kv: kv[1]):
        print(f"  {name:<24} {avg:.2f}/10")
    print(f"\nWrote {csv_path}")
    print(f"Wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
