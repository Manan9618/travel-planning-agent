from datetime import date

import folium
import pytest
from folium.plugins import MarkerCluster, TimestampedGeoJson

from travel_agent.models.core import (
    DayPlan,
    HotelOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
)
from travel_agent.tools.travel_map_generator import (
    DAY_COLORS,
    TravelMapGenerator,
    day_color,
)


def _prefs():
    return TravelPreferences(destination="Paris", start_date=date(2026, 9, 1), raw_text="t")


def _hotel(lat=48.85, lng=2.35):
    return HotelOption(
        name="Test Hotel", address="Paris, France", lat=lat, lng=lng, price_per_night=100
    )


def _item(title, lat, lng, activity_type="attraction", start="2026-09-02T09:00:00", cost=None):
    return ItineraryItem(
        time_slot="morning",
        start_time=start,
        end_time=start,
        activity_type=activity_type,
        title=title,
        lat=lat,
        lng=lng,
        cost=cost,
    )


def _markers(fmap: folium.Map) -> list[folium.Marker]:
    markers = []
    for child in fmap._children.values():
        if isinstance(child, MarkerCluster):
            markers.extend(c for c in child._children.values() if isinstance(c, folium.Marker))
        elif isinstance(child, folium.Marker):
            markers.append(child)
    return markers


def _polylines(fmap: folium.Map) -> list[folium.PolyLine]:
    return [c for c in fmap._children.values() if isinstance(c, folium.PolyLine)]


def _timelines(fmap: folium.Map) -> list[TimestampedGeoJson]:
    return [c for c in fmap._children.values() if isinstance(c, TimestampedGeoJson)]


# --- day_color -------------------------------------------------------------


def test_day_color_cycles_through_palette():
    assert day_color(1) == DAY_COLORS[0]
    assert day_color(2) == DAY_COLORS[1]
    assert day_color(len(DAY_COLORS) + 1) == DAY_COLORS[0]  # wraps around


# --- generate() structure ---------------------------------------------------


def test_generate_returns_a_folium_map():
    itinerary = Itinerary(preferences=_prefs(), days=[], hotel=_hotel())
    fmap = TravelMapGenerator().generate(itinerary)
    assert isinstance(fmap, folium.Map)


def test_generate_includes_a_hotel_marker():
    itinerary = Itinerary(preferences=_prefs(), days=[], hotel=_hotel())
    fmap = TravelMapGenerator().generate(itinerary)
    markers = _markers(fmap)
    assert len(markers) == 1
    assert markers[0].location == [48.85, 2.35]


def test_generate_skips_hotel_marker_when_no_hotel():
    itinerary = Itinerary(preferences=_prefs(), days=[])
    fmap = TravelMapGenerator().generate(itinerary)
    assert _markers(fmap) == []


def test_generate_adds_one_marker_per_scheduled_item_with_coordinates():
    day = DayPlan(
        day_number=2,
        date=date(2026, 9, 2),
        items=[
            _item("Louvre", 48.86, 2.33),
            _item("Cafe", 48.85, 2.35, activity_type="restaurant"),
            ItineraryItem(  # no lat/lng -> should be skipped
                time_slot="morning",
                start_time="2026-09-02T08:00:00",
                end_time="2026-09-02T08:00:00",
                activity_type="transfer",
                title="Airport transfer",
            ),
        ],
    )
    itinerary = Itinerary(preferences=_prefs(), days=[day])
    fmap = TravelMapGenerator().generate(itinerary)
    assert len(_markers(fmap)) == 2


def _popup_html(marker: folium.Marker) -> str:
    popup = next(c for c in marker._children.values() if isinstance(c, folium.Popup))
    return popup.get_root().render()


def test_marker_popup_includes_day_number_and_title():
    day = DayPlan(day_number=3, date=date(2026, 9, 3), items=[_item("Eiffel Tower", 48.86, 2.29)])
    itinerary = Itinerary(preferences=_prefs(), days=[day])
    fmap = TravelMapGenerator().generate(itinerary)
    popup_html = _popup_html(_markers(fmap)[0])
    assert "Day 3" in popup_html
    assert "Eiffel Tower" in popup_html


def test_marker_popup_includes_cost_when_present():
    day = DayPlan(
        day_number=1, date=date(2026, 9, 1), items=[_item("Museum", 48.86, 2.33, cost=25)]
    )
    itinerary = Itinerary(preferences=_prefs(), days=[day])
    fmap = TravelMapGenerator().generate(itinerary)
    popup_html = _popup_html(_markers(fmap)[0])
    assert "$25" in popup_html


# --- day routes (polylines) --------------------------------------------------


def test_route_polyline_added_when_day_has_two_or_more_points():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("A", 48.86, 2.33), _item("B", 48.85, 2.34)],
    )
    itinerary = Itinerary(preferences=_prefs(), days=[day])
    fmap = TravelMapGenerator().generate(itinerary)
    assert len(_polylines(fmap)) == 1


def test_no_route_polyline_when_day_has_fewer_than_two_points():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("A", 48.86, 2.33)])
    itinerary = Itinerary(preferences=_prefs(), days=[day])
    fmap = TravelMapGenerator().generate(itinerary)
    assert _polylines(fmap) == []


def test_each_day_gets_its_own_polyline():
    day1 = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("A", 48.86, 2.33), _item("B", 48.85, 2.34)],
    )
    day2 = DayPlan(
        day_number=2,
        date=date(2026, 9, 2),
        items=[_item("C", 48.87, 2.31), _item("D", 48.88, 2.30)],
    )
    itinerary = Itinerary(preferences=_prefs(), days=[day1, day2])
    fmap = TravelMapGenerator().generate(itinerary)
    assert len(_polylines(fmap)) == 2


# --- timeline (day-by-day reveal animation) -----------------------------------


def test_timeline_added_when_at_least_one_day_has_a_route():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("A", 48.86, 2.33), _item("B", 48.85, 2.34)],
    )
    itinerary = Itinerary(preferences=_prefs(), days=[day])
    fmap = TravelMapGenerator().generate(itinerary)
    assert len(_timelines(fmap)) == 1


def test_no_timeline_when_no_day_has_a_multi_point_route():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("A", 48.86, 2.33)])
    itinerary = Itinerary(preferences=_prefs(), days=[day])
    fmap = TravelMapGenerator().generate(itinerary)
    assert _timelines(fmap) == []


# --- render_html / save -------------------------------------------------------


def test_render_html_returns_nonempty_string_containing_leaflet():
    itinerary = Itinerary(preferences=_prefs(), days=[], hotel=_hotel())
    html = TravelMapGenerator().render_html(itinerary)
    assert isinstance(html, str)
    assert "leaflet" in html.lower()


def test_save_writes_a_file_and_returns_its_path(tmp_path):
    itinerary = Itinerary(preferences=_prefs(), days=[], hotel=_hotel())
    out_path = tmp_path / "nested" / "map.html"
    result = TravelMapGenerator().save(itinerary, out_path)
    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0


# --- render_thumbnail_png (real headless-browser rasterization) --------------


def test_render_thumbnail_png_produces_a_nonempty_png(tmp_path):
    pytest.importorskip("playwright")
    from travel_agent.tools.travel_map_generator import render_thumbnail_png

    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("A", 48.86, 2.33), _item("B", 48.85, 2.34)],
    )
    itinerary = Itinerary(preferences=_prefs(), days=[day], hotel=_hotel())
    html_path = tmp_path / "map.html"
    png_path = tmp_path / "thumb.png"

    TravelMapGenerator().save(itinerary, html_path)
    render_thumbnail_png(html_path, png_path, width=400, height=300, wait_ms=300)

    assert png_path.exists()
    assert png_path.stat().st_size > 1000  # a real screenshot, not an empty/corrupt file
