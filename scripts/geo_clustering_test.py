#!/usr/bin/env python3
"""Week 9 deliverable: geospatial data pipeline verification across 3 cities.

Fetches real attractions (AttractionFinderTool/Serper — already geocoded, no
separate enrichment step needed), computes the full travel-time matrix between
them (DistanceMatrixTool), clusters them with DBSCAN (haversine metric, so `eps`
is real-world km), and renders a color-coded Folium map per city. Maps are saved
under output/geo_clusters/ (gitignored — these are generated artifacts, not
source) so they can be opened and visually inspected.

Usage:
    poetry run python scripts/geo_clustering_test.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, "src")

from travel_agent.tools.attraction_finder import AttractionFinderTool  # noqa: E402
from travel_agent.tools.distance_matrix import DistanceMatrixTool  # noqa: E402
from travel_agent.tools.geo_clustering import (  # noqa: E402
    cluster_attractions,
    cluster_summary,
    render_cluster_map,
)

CITIES = ["Paris", "Tokyo", "New York"]
OUTPUT_DIR = Path("output/geo_clusters")


def _haversine_km(a, b) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def run_city(city: str) -> None:
    print(f"\n{'=' * 70}\n{city}\n{'=' * 70}")
    attractions = AttractionFinderTool().search(city, max_results=15)
    points = [(a.lat, a.lng) for a in attractions]

    matrix = DistanceMatrixTool().compute_matrix(points)
    avg_minutes = sum(sum(row) for row in matrix) / (len(points) * (len(points) - 1))
    print(f"{len(points)} attractions; average pairwise travel time: {avg_minutes:.1f} min")

    labels = cluster_attractions(attractions)
    summary = cluster_summary(attractions, labels)
    num_clusters = len({label for label in labels if label != -1})
    num_noise = sum(1 for label in labels if label == -1)
    print(f"{num_clusters} clusters found, {num_noise} isolated (noise) attraction(s)")

    for cluster_id in sorted(summary):
        names = summary[cluster_id]
        if cluster_id == -1:
            print(f"  NOISE: {', '.join(names)}")
            continue
        members = [a for a, label in zip(attractions, labels, strict=True) if label == cluster_id]
        max_span = max(
            (_haversine_km((m1.lat, m1.lng), (m2.lat, m2.lng)) for m1 in members for m2 in members),
            default=0.0,
        )
        print(f"  Cluster {cluster_id} (span {max_span:.2f} km): {', '.join(names)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{city.lower().replace(' ', '_')}.html"
    render_cluster_map(attractions, labels).save(str(out_path))
    print(f"Map saved to {out_path}")


def main() -> int:
    for city in CITIES:
        run_city(city)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
