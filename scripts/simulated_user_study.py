#!/usr/bin/env python3
"""Week 22 deliverable: SIMULATED user study.

The plan calls for "5 friends/family use the app, collect qualitative
feedback." This project has no real testers available to recruit, and
fabricating a "5 real people used the app" claim would contradict the
project's own consistent practice of only reporting real, live-verified
results. Per explicit direction, this substitutes 5 diverse LLM personas
that drive the REAL pipeline end to end (real PreferenceParser NLU parsing
of a natural-language request, real Serper/Booking.com/OpenWeatherMap calls,
real MultiDayOptimizer) and then give first-person qualitative feedback via
a separate GPT-4o call, clearly roleplaying a distinct traveler type.

THIS IS NOT A REAL USER STUDY. Every persona, its preferences, and its
feedback are LLM-generated. Reported everywhere (README, evaluation report)
as "simulated," never as real user research — see the Week 22 evaluation
report's Limitations section for why this substitution was made and what it
can and can't tell you (it exercises the real pipeline and can surface real
usability gaps a persona's stated priorities would care about, but it cannot
substitute for how an actual human reacts to actually using the product).

Outputs:
    output/evaluation/simulated_user_study.json
    output/evaluation/simulated_user_study.html

Usage:
    poetry run python scripts/simulated_user_study.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "src")

from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from travel_agent.config import settings  # noqa: E402
from travel_agent.tools.attraction_finder import AttractionFinderTool  # noqa: E402
from travel_agent.tools.hotel_search import HotelSearchTool  # noqa: E402
from travel_agent.tools.itinerary_judge import render_itinerary_summary  # noqa: E402
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer  # noqa: E402
from travel_agent.tools.preference_parser import PreferenceParser  # noqa: E402
from travel_agent.tools.restaurant_finder import RestaurantFinderTool  # noqa: E402
from travel_agent.tools.weather_checker import WeatherCheckerTool  # noqa: E402

OUTPUT_DIR = Path("output/evaluation")
START = date.today() + timedelta(days=45)

# Each persona has a name/description (used only to prompt the review call)
# and a genuine natural-language trip request, parsed by the REAL
# PreferenceParser like any real /plan request would be - nothing here is
# hand-built TravelPreferences.
PERSONAS = [
    (
        "Budget Backpacker Ben",
        "a broke solo backpacker who prioritizes authentic local experiences and cheap "
        "hostels over comfort, and gets annoyed by anything that feels touristy or overpriced",
        f"I'm a broke backpacker heading to Bangkok for 6 days starting "
        f"{START.isoformat()}, budget is $800, I want street food and cheap hostels, "
        "love adventure and local culture, keep it packed",
    ),
    (
        "Luxury Honeymooners Priya & Alex",
        "a newly-married couple on their honeymoon who expect a flawless, romantic, "
        "high-end experience and are disappointed by anything that feels budget or rushed",
        f"My partner and I are on our honeymoon, 5 days in Santorini starting "
        f"{START.isoformat()}, budget $5000, we want the most romantic, relaxed, "
        "luxurious experience possible with amazing views and fine dining",
    ),
    (
        "Family Planner Maria",
        "a parent planning a trip with two young kids (ages 7 and 10) who cares most "
        "about pacing that won't exhaust the kids and activities the whole family enjoys",
        f"Planning a 6 day family trip to Orlando with my husband and 2 kids (ages 7 "
        f"and 10) starting {START.isoformat()}, budget $3500, we want theme parks and "
        "kid-friendly activities, relaxed pace, nothing too intense",
    ),
    (
        "Solo Adventurer Jake",
        "an experienced solo traveler who wants an active, physically demanding trip "
        "and would be bored by a slow, sightseeing-only itinerary",
        f"Solo adventure trip to Reykjavik for 5 days starting {START.isoformat()}, "
        "budget $3000, I want hiking, nature, a packed schedule, and a shot at seeing "
        "the northern lights",
    ),
    (
        "Business Traveler David",
        "a business traveler with limited free time who values efficiency and "
        "convenience over novelty, and is frustrated by anything that wastes his time",
        f"Business trip to Sydney for 4 days starting {START.isoformat()}, budget "
        "$3500, need an efficient schedule I can fit around meetings, good networking "
        "spots for dinner, comfortable but not extravagant",
    ),
]


class PersonaFeedback(BaseModel):
    satisfaction: int = Field(ge=1, le=10)
    liked: str = Field(description="1-2 sentences on what this traveler liked")
    disliked: str = Field(
        description="1-2 sentences on what this traveler didn't like or wanted changed"
    )
    would_use_again: bool


def _collect_feedback(persona_name: str, persona_description: str, summary: str) -> PersonaFeedback:
    llm = ChatOpenAI(
        model=settings.openai_model, temperature=0.7, api_key=settings.openai_api_key or None
    ).with_structured_output(PersonaFeedback)
    system = (
        f"You are {persona_name}: {persona_description}. You just received this "
        "AI-generated travel itinerary for the exact trip you asked for. React as this "
        "specific traveler would, honestly - including real criticism if the plan "
        "doesn't fit what you care about. Do not be uniformly positive."
    )
    result = llm.invoke([("system", system), ("human", summary)])
    if not isinstance(result, PersonaFeedback):
        raise ValueError("LLM did not return structured output")
    return result


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parser = PreferenceParser()
    optimizer = MultiDayOptimizer()
    weather_tool = WeatherCheckerTool()

    results = []
    for persona_name, persona_description, raw_text in PERSONAS:
        print(f"\n=== {persona_name} ===")
        prefs = parser.parse(raw_text)
        print(f"  Parsed: {prefs.destination}, {prefs.duration_days}d, ${prefs.budget_total}")

        attractions = AttractionFinderTool().search(
            prefs.destination, interests=prefs.interests, max_results=14
        )
        restaurants = RestaurantFinderTool().search(prefs.destination, max_results=14)
        check_out = prefs.start_date + timedelta(days=prefs.duration_days)
        hotel = HotelSearchTool().search(
            prefs.destination, prefs.start_date, check_out, budget_tier=prefs.budget_tier
        )[0]
        weather = weather_tool.get_forecast(
            prefs.destination,
            prefs.start_date,
            prefs.start_date + timedelta(days=prefs.duration_days - 1),
        )

        itinerary = optimizer.build(prefs, hotel, attractions, restaurants, weather=weather)
        summary = render_itinerary_summary(prefs, itinerary)

        feedback = _collect_feedback(persona_name, persona_description, summary)
        print(f"  Satisfaction: {feedback.satisfaction}/10")
        print(f"  Liked: {feedback.liked}")
        print(f"  Disliked: {feedback.disliked}")

        results.append(
            {
                "persona": persona_name,
                "persona_description": persona_description,
                "request": raw_text,
                "destination": prefs.destination,
                "satisfaction": feedback.satisfaction,
                "liked": feedback.liked,
                "disliked": feedback.disliked,
                "would_use_again": feedback.would_use_again,
            }
        )

    avg_satisfaction = sum(r["satisfaction"] for r in results) / len(results)
    would_use_again_rate = sum(r["would_use_again"] for r in results) / len(results)

    json_path = OUTPUT_DIR / "simulated_user_study.json"
    json_path.write_text(
        json.dumps(
            {
                "SIMULATED": True,
                "disclaimer": (
                    "All personas and feedback below are LLM-generated roleplay, not "
                    "real human testers. See scripts/simulated_user_study.py and the "
                    "Week 22 evaluation report for why."
                ),
                "average_satisfaction": avg_satisfaction,
                "would_use_again_rate": would_use_again_rate,
                "results": results,
            },
            indent=2,
        )
    )

    rows_html = "".join(
        f"<tr><td>{r['persona']}</td><td>{r['destination']}</td>"
        f"<td>{r['satisfaction']}/10</td><td>{'Yes' if r['would_use_again'] else 'No'}</td>"
        f"<td>{r['liked']}</td><td>{r['disliked']}</td></tr>"
        for r in results
    )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Simulated User Study (Week 22)</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; }}
.banner {{ background: #fff3cd; border: 1px solid #ffe08a; padding: 1rem; margin-bottom: 1rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; vertical-align: top; }}
th {{ background: #f0f0f0; }}
</style></head>
<body>
<div class="banner"><b>SIMULATED, not a real user study.</b> All 5 personas and their
feedback below are LLM-generated roleplay driving the real pipeline end to end - see
scripts/simulated_user_study.py's module docstring for why this substitution was made.</div>
<h1>Simulated User Study — Week 22</h1>
<p>Average satisfaction: <b>{avg_satisfaction:.1f}/10</b> — would use again:
<b>{would_use_again_rate:.0%}</b></p>
<table>
<tr><th>Persona</th><th>Destination</th><th>Satisfaction</th><th>Would use again</th>
<th>Liked</th><th>Disliked</th></tr>
{rows_html}
</table>
</body></html>
"""
    html_path = OUTPUT_DIR / "simulated_user_study.html"
    html_path.write_text(html)

    print("\n" + "-" * 60)
    print(f"Average satisfaction: {avg_satisfaction:.1f}/10")
    print(f"Would use again: {would_use_again_rate:.0%}")
    print(f"\nWrote {json_path}")
    print(f"Wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
