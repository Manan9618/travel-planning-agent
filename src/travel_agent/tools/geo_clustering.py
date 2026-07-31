"""Geospatial clustering — Week 9 deliverable.

Groups nearby attractions using DBSCAN with a haversine metric, so `eps` is a
real-world distance in km rather than raw lat/lng degrees. Plain Euclidean
distance on degrees would systematically distort: a degree of longitude is
~111km at the equator but shrinks toward the poles, while a degree of latitude
stays ~111km everywhere — cities at different latitudes (Paris ~49N, Tokyo ~36N,
New York ~41N) would get inconsistently-shaped clusters if that distortion went
uncorrected. Haversine on radians (with eps converted from km via Earth's radius)
avoids it.
"""

from __future__ import annotations

import folium
import numpy as np
from sklearn.cluster import DBSCAN

from travel_agent.models.core import Attraction

EARTH_RADIUS_KM = 6371.0
DEFAULT_EPS_KM = 1.5
DEFAULT_MIN_SAMPLES = 2

_PALETTE = [
    "red",
    "blue",
    "green",
    "purple",
    "orange",
    "darkred",
    "cadetblue",
    "darkgreen",
    "pink",
    "gray",
]


def cluster_attractions(
    attractions: list[Attraction],
    eps_km: float = DEFAULT_EPS_KM,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> list[int]:
    """One cluster label per attraction, same order as `attractions`. -1 is
    DBSCAN's "noise" label (not enough nearby neighbors to join a cluster) —
    not an error, just an isolated point.
    """
    if not attractions:
        return []
    coords_rad = np.radians([[a.lat, a.lng] for a in attractions])
    labels = DBSCAN(
        eps=eps_km / EARTH_RADIUS_KM, min_samples=min_samples, metric="haversine"
    ).fit_predict(coords_rad)
    return labels.tolist()


def cluster_summary(attractions: list[Attraction], labels: list[int]) -> dict[int, list[str]]:
    """Cluster id -> attraction names in that cluster, for inspection/reporting."""
    groups: dict[int, list[str]] = {}
    for attraction, label in zip(attractions, labels, strict=True):
        groups.setdefault(label, []).append(attraction.name)
    return groups


def render_cluster_map(attractions: list[Attraction], labels: list[int]) -> folium.Map:
    if not attractions:
        raise ValueError("no attractions to render")
    center = (
        sum(a.lat for a in attractions) / len(attractions),
        sum(a.lng for a in attractions) / len(attractions),
    )
    fmap = folium.Map(location=center, zoom_start=13)
    for attraction, label in zip(attractions, labels, strict=True):
        color = "black" if label == -1 else _PALETTE[label % len(_PALETTE)]
        folium.CircleMarker(
            location=(attraction.lat, attraction.lng),
            radius=8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=f"{attraction.name} (cluster {label})",
        ).add_to(fmap)
    return fmap
