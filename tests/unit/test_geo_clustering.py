import folium
import pytest

from travel_agent.models.core import Attraction
from travel_agent.tools.geo_clustering import (
    cluster_attractions,
    cluster_summary,
    render_cluster_map,
)


def _attraction(name, lat, lng):
    return Attraction(name=name, lat=lat, lng=lng)


def test_empty_list_returns_empty_labels():
    assert cluster_attractions([]) == []


def test_two_nearby_points_cluster_together():
    # ~100m apart (0.001 deg lat ~ 111m) — well within the 1.5km default eps
    attractions = [
        _attraction("A", 48.8566, 2.3522),
        _attraction("B", 48.8576, 2.3522),
    ]
    labels = cluster_attractions(attractions, min_samples=2)
    assert labels[0] == labels[1]
    assert labels[0] != -1


def test_two_far_points_are_noise_with_min_samples_two():
    # roughly 100km apart in latitude alone, far beyond the default 1.5km eps
    attractions = [
        _attraction("A", 48.0, 2.35),
        _attraction("B", 49.0, 2.35),
    ]
    labels = cluster_attractions(attractions, min_samples=2)
    assert labels == [-1, -1]  # each has no neighbor within eps, so neither can form a cluster


def test_mixed_near_and_far_points():
    attractions = [
        _attraction("Near1", 48.8566, 2.3522),
        _attraction("Near2", 48.8576, 2.3522),
        _attraction("Far", 35.6762, 139.6503),  # Tokyo, nowhere near Paris
    ]
    labels = cluster_attractions(attractions, min_samples=2)
    assert labels[0] == labels[1]
    assert labels[0] != -1
    assert labels[2] == -1


def test_min_samples_one_means_no_noise():
    attractions = [
        _attraction("A", 48.0, 2.35),
        _attraction("B", 49.0, 2.35),
    ]
    labels = cluster_attractions(attractions, min_samples=1)
    assert -1 not in labels  # every point is its own valid cluster when min_samples=1


def test_large_eps_groups_everything_together():
    attractions = [
        _attraction("Paris", 48.8566, 2.3522),
        _attraction("Tokyo", 35.6762, 139.6503),
    ]
    labels = cluster_attractions(attractions, eps_km=20_000, min_samples=2)
    assert labels[0] == labels[1] != -1


def test_haversine_scaling_is_correct_not_euclidean_on_degrees():
    # two points exactly ~111km apart (1 degree of latitude); eps_km=50 should NOT
    # cluster them (they're father apart than 50km), eps_km=200 should.
    attractions = [
        _attraction("A", 48.0, 2.35),
        _attraction("B", 49.0, 2.35),
    ]
    assert cluster_attractions(attractions, eps_km=50, min_samples=2) == [-1, -1]
    labels = cluster_attractions(attractions, eps_km=200, min_samples=2)
    assert labels[0] == labels[1] != -1


def test_cluster_summary_groups_names_by_label():
    attractions = [
        _attraction("A", 48.8566, 2.3522),
        _attraction("B", 48.8576, 2.3522),
        _attraction("C", 35.6762, 139.6503),
    ]
    labels = [0, 0, -1]
    summary = cluster_summary(attractions, labels)
    assert summary[0] == ["A", "B"]
    assert summary[-1] == ["C"]


def test_render_cluster_map_returns_folium_map():
    attractions = [_attraction("A", 48.8566, 2.3522), _attraction("B", 48.8576, 2.3522)]
    fmap = render_cluster_map(attractions, [0, 0])
    assert isinstance(fmap, folium.Map)


def test_render_cluster_map_empty_raises():
    with pytest.raises(ValueError):
        render_cluster_map([], [])


def test_render_cluster_map_includes_a_marker_per_attraction():
    attractions = [
        _attraction("A", 48.8566, 2.3522),
        _attraction("B", 48.8576, 2.3522),
        _attraction("C", 35.6762, 139.6503),
    ]
    fmap = render_cluster_map(attractions, [0, 0, -1])
    markers = [c for c in fmap._children.values() if isinstance(c, folium.CircleMarker)]
    assert len(markers) == 3
