#!/usr/bin/env python3
"""Week 10 deliverable: benchmark NN+2-opt route optimization against naive
(random) ordering across 20 scenarios.

5 real cities x 4 activity-subset sizes each = 20 scenarios. Attractions are
fetched once per city (real data via AttractionFinderTool/Serper) and reused
across that city's scenarios to keep this fast; each scenario builds its own
real Distance Matrix (cached — see DistanceMatrixTool) for the specific subset
of attractions plus a hotel anchor point. The naive baseline is the average of
10 random shuffles per scenario, rather than a single shuffle, so a lucky/unlucky
draw doesn't skew the reported improvement.

Usage:
    poetry run python scripts/route_optimization_benchmark.py
"""

from __future__ import annotations

import random
import sys

sys.path.insert(0, "src")

from travel_agent.tools.attraction_finder import AttractionFinderTool  # noqa: E402
from travel_agent.tools.distance_matrix import DistanceMatrixTool  # noqa: E402
from travel_agent.tools.route_optimizer import (  # noqa: E402
    RouteOptimizerTool,
    random_tour,
    tour_length,
)

CITIES = ["Paris", "London", "Tokyo", "Rome", "Barcelona"]
SUBSET_SIZES = [4, 6, 8, 10]
RANDOM_BASELINE_SAMPLES = 10
RNG_SEED = 42


def _city_center(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def run_scenario(city: str, attractions, subset_size: int, rng: random.Random) -> float:
    subset = attractions[:subset_size]
    attraction_points = [(a.lat, a.lng) for a in subset]
    hotel_point = _city_center(attraction_points)  # a stand-in central hotel location
    points = [hotel_point] + attraction_points

    matrix = DistanceMatrixTool().compute_matrix(points)
    optimizer = RouteOptimizerTool()
    optimized = optimizer.optimize(matrix)

    naive_lengths = [
        tour_length(matrix, random_tour(len(points), rng=rng))
        for _ in range(RANDOM_BASELINE_SAMPLES)
    ]
    avg_naive_length = sum(naive_lengths) / len(naive_lengths)
    optimized_length = tour_length(matrix, optimized)
    return avg_naive_length / optimized_length if optimized_length > 0 else 1.0


def main() -> int:
    rng = random.Random(RNG_SEED)
    print(f"{'City':<12} {'Activities':>10} {'Efficiency Gain':>16}")
    print("-" * 42)

    scores = []
    for city in CITIES:
        attractions = AttractionFinderTool().search(city, max_results=max(SUBSET_SIZES))
        for size in SUBSET_SIZES:
            if len(attractions) < size:
                continue
            score = run_scenario(city, attractions, size, rng)
            scores.append(score)
            print(f"{city:<12} {size:>10} {score - 1:>+15.0%}")

    print("-" * 42)
    print(f"{'AVERAGE IMPROVEMENT':<12} {'':>10} {sum(scores) / len(scores) - 1:>+15.0%}")
    print(f"({len(scores)} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
