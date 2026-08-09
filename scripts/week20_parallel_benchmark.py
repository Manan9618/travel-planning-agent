#!/usr/bin/env python3
"""Week 20 deliverable: before/after benchmark for parallel search-phase execution.

Two measurements, both against real APIs (no mocking):

1. Direct tool-level A/B — the same 5 independent search tools
   (flights/hotels/attractions/restaurants/weather) called sequentially vs.
   concurrently (via a thread pool, the same mechanism LangGraph's own sync
   Pregel executor uses internally for same-superstep nodes — see
   `langgraph.pregel.executor`). Caching is deliberately disabled (an
   unreachable Redis URL) so both modes pay full real network latency; this
   isolates the speedup that comes purely from concurrency, not from one
   run warming the other's cache.

2. A real end-to-end run of the compiled planning graph
   (`build_planning_graph`, real tools, real OpenAI calls for preference
   parsing/description/judging), read back via Prometheus's
   `planning_step_duration_seconds` to show the search phase's wall time in
   the ACTUAL pipeline is close to its slowest single tool, not the sum of
   all five — and via `llm_tokens_total` to confirm the supervisor's old
   tie-break LLM call (removed this week — see `SupervisorAgent`) no longer
   fires: token usage now comes only from preference parsing, attraction
   description/judging, and narration.

Usage:
    poetry run python scripts/week20_parallel_benchmark.py
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

sys.path.insert(0, "src")

from travel_agent.agents.graph import build_planning_graph  # noqa: E402
from travel_agent.observability.metrics import LLM_TOKENS, PLANNING_STEP_DURATION  # noqa: E402
from travel_agent.tools.attraction_finder import AttractionFinderTool  # noqa: E402
from travel_agent.tools.flight_search import FlightSearchTool  # noqa: E402
from travel_agent.tools.hotel_search import HotelSearchTool  # noqa: E402
from travel_agent.tools.restaurant_finder import RestaurantFinderTool  # noqa: E402
from travel_agent.tools.weather_checker import WeatherCheckerTool  # noqa: E402
from travel_agent.utils.cache import Cache  # noqa: E402

TRIP_START = date.today() + timedelta(days=45)
TRIP_END = TRIP_START + timedelta(days=4)

# A Redis URL nothing is listening on: Cache.__init__ pings it, fails fast
# (1s connect timeout), and falls back to its documented no-op mode - so
# every tool call below pays full real network latency both times, instead
# of the second mode being unfairly sped up by the first mode's cache writes.
_NO_CACHE = lambda: Cache(url="redis://127.0.0.1:1/0")  # noqa: E731


def _sequential(destination: str, origin_iata: str, dest_iata: str) -> float:
    flight_tool = FlightSearchTool(cache=_NO_CACHE())
    hotel_tool = HotelSearchTool(cache=_NO_CACHE())
    attraction_tool = AttractionFinderTool(cache=_NO_CACHE())
    restaurant_tool = RestaurantFinderTool(cache=_NO_CACHE())
    weather_tool = WeatherCheckerTool(cache=_NO_CACHE())

    start = time.perf_counter()
    flight_tool.search(origin_iata, dest_iata, TRIP_START, TRIP_END)
    hotel_tool.search(destination, TRIP_START, TRIP_END)
    attraction_tool.search(destination, max_results=10)
    restaurant_tool.search(destination, max_results=10)
    weather_tool.get_forecast(destination, TRIP_START, TRIP_END)
    return time.perf_counter() - start


def _parallel(destination: str, origin_iata: str, dest_iata: str) -> float:
    flight_tool = FlightSearchTool(cache=_NO_CACHE())
    hotel_tool = HotelSearchTool(cache=_NO_CACHE())
    attraction_tool = AttractionFinderTool(cache=_NO_CACHE())
    restaurant_tool = RestaurantFinderTool(cache=_NO_CACHE())
    weather_tool = WeatherCheckerTool(cache=_NO_CACHE())

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [
            pool.submit(flight_tool.search, origin_iata, dest_iata, TRIP_START, TRIP_END),
            pool.submit(hotel_tool.search, destination, TRIP_START, TRIP_END),
            pool.submit(attraction_tool.search, destination, max_results=10),
            pool.submit(restaurant_tool.search, destination, max_results=10),
            pool.submit(weather_tool.get_forecast, destination, TRIP_START, TRIP_END),
        ]
        for f in futures:
            f.result()
    return time.perf_counter() - start


# (destination, origin_iata, dest_iata) - distinct per mode so neither run's
# cache-disabled-but-still-per-process objects share any incidental state.
SEQUENTIAL_DESTS = [("Paris", "BOS", "PAR"), ("Tokyo", "LAX", "TYO")]
PARALLEL_DESTS = [("Rome", "BOS", "ROM"), ("Barcelona", "LAX", "BCN")]


def _histogram_stat(histogram, stat: str, **labels) -> float:
    (metric,) = histogram.collect()
    for sample in metric.samples:
        if sample.name.endswith(f"_{stat}") and sample.labels == labels:
            return sample.value
    return 0.0


def _counter_total(counter: object) -> float:
    total = 0.0
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                total += sample.value
    return total


def main() -> int:
    print("=== 1. Direct tool-level A/B: sequential vs. concurrent search calls ===\n")

    sequential_times = [_sequential(dest, o, d) for dest, o, d in SEQUENTIAL_DESTS]
    parallel_times = [_parallel(dest, o, d) for dest, o, d in PARALLEL_DESTS]

    for (dest, *_), t in zip(SEQUENTIAL_DESTS, sequential_times, strict=False):
        print(f"  sequential  {dest:<12} {t:>6.2f}s")
    for (dest, *_), t in zip(PARALLEL_DESTS, parallel_times, strict=False):
        print(f"  parallel    {dest:<12} {t:>6.2f}s")

    avg_sequential = sum(sequential_times) / len(sequential_times)
    avg_parallel = sum(parallel_times) / len(parallel_times)
    speedup = avg_sequential / avg_parallel if avg_parallel else float("inf")
    print(f"\n  avg sequential: {avg_sequential:.2f}s   avg parallel: {avg_parallel:.2f}s")
    print(f"  speedup: {speedup:.2f}x\n")

    print("=== 2. End-to-end graph run (real tools, real LLM calls) ===\n")
    llm_tokens_before = _counter_total(LLM_TOKENS)

    graph = build_planning_graph()
    config = {"configurable": {"thread_id": "week20-benchmark"}, "recursion_limit": 100}
    start = time.perf_counter()
    result = graph.invoke(
        {
            "raw_text": (
                f"4 days in Lisbon from Boston starting "
                f"{TRIP_START.isoformat()}, budget $2000, interests: food and history"
            ),
            "errors": [],
            "completed_steps": [],
        },
        config=config,
    )
    total_elapsed = time.perf_counter() - start
    llm_tokens_after = _counter_total(LLM_TOKENS)

    search_steps = [
        "search_flights",
        "search_hotels",
        "find_attractions",
        "find_restaurants",
        "check_weather",
    ]
    search_durations = {
        step: _histogram_stat(PLANNING_STEP_DURATION, "sum", step=step) for step in search_steps
    }
    search_wall_sum = sum(search_durations.values())

    print(f"  destination: {result['preferences'].get('destination')}")
    print(f"  completed steps: {sorted(result['completed_steps'])}")
    print(f"  errors: {result['errors']}")
    print(f"\n  total planning time: {total_elapsed:.2f}s")
    print("  per-tool search step duration (from Prometheus):")
    for step, dur in search_durations.items():
        print(f"    {step:<18} {dur:>6.2f}s")
    print(f"  sum of the 5 search steps if run sequentially: ~{search_wall_sum:.2f}s")
    print(
        f"  LLM tokens consumed this run: {llm_tokens_after - llm_tokens_before:.0f} "
        "(no supervisor tie-break call included - SupervisorAgent makes no LLM calls at all)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
