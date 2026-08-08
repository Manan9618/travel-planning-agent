"""TravelMapGenerator — Week 13 deliverable.

Renders a built Itinerary as an interactive Folium/Leaflet map: a hotel
marker, one marker per scheduled attraction/restaurant/hotel check-in/out —
color-coded by day along a sequential blue-to-amber ramp (`DAY_COLORS`, Day 1
= blue through the trip's final day = amber) with a popup info card — a
polyline per day connecting that day's stops in chronological order, marker
clustering (so the map stays readable zoomed out), and a day-by-day reveal
animation via Folium's `TimestampedGeoJson` plugin (a real Leaflet timeline
control — every day's route feature shares one timestamp, so advancing the
slider reveals a full day's route at once and earlier days stay visible,
rather than animating point-by-point).

Markers use `CircleMarker` (a plain colored dot) rather than `Marker` +
`Icon`: Folium's `Icon` only accepts a small fixed set of named colors (no
arbitrary hex), which can't represent a smooth ramp — `CircleMarker` takes
any hex color and is also what the Week 16 React frontend's live map preview
already uses, so a day's color reads identically across both.

`render_thumbnail_png()` rasterizes a saved map HTML file via a headless
Chromium (Playwright) — needed because Week 14's PDF renderer can't embed
live Leaflet JS, only a static image.
"""

from __future__ import annotations

from pathlib import Path

import folium
from folium.plugins import MarkerCluster, TimestampedGeoJson

from travel_agent.models.core import DayPlan, Itinerary, ItineraryItem

# A sequential blue -> amber ramp (HSL hue 214 -> 36, s=58%, l=46%), so day
# color reads as a natural progression through the trip rather than an
# arbitrary categorical palette — matches the same ramp in the frontend's
# dayColors.ts, kept in sync by hand (same cross-language duplication this
# project already accepts for e.g. PlanningStep's string values).
DAY_COLORS = [
    "#316cb9",
    "#3199b9",
    "#31b9ad",
    "#31b980",
    "#31b953",
    "#3cb931",
    "#69b931",
    "#96b931",
    "#b9b031",
    "#b98331",
]
HOTEL_MARKER_COLOR = "#111827"
DEFAULT_ZOOM = 13


def day_color(day_number: int) -> str:
    return DAY_COLORS[(day_number - 1) % len(DAY_COLORS)]


class TravelMapGenerator:
    def generate(self, itinerary: Itinerary) -> folium.Map:
        fmap = folium.Map(location=self._center(itinerary), zoom_start=DEFAULT_ZOOM)
        cluster = MarkerCluster(name="Stops").add_to(fmap)

        if itinerary.hotel:
            self._add_hotel_marker(itinerary, cluster)
        for day in itinerary.days:
            self._add_day_markers(day, cluster)
            self._add_day_route(day, fmap)

        self._add_timeline(itinerary, fmap)
        folium.LayerControl().add_to(fmap)
        return fmap

    def render_html(self, itinerary: Itinerary) -> str:
        return self.generate(itinerary).get_root().render()

    def save(self, itinerary: Itinerary, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.generate(itinerary).save(str(path))
        return path

    # --- internals -----------------------------------------------------

    @staticmethod
    def _center(itinerary: Itinerary) -> tuple[float, float]:
        points = []
        if itinerary.hotel:
            points.append((itinerary.hotel.lat, itinerary.hotel.lng))
        for day in itinerary.days:
            for item in day.items:
                if item.lat is not None and item.lng is not None:
                    points.append((item.lat, item.lng))
        if not points:
            return (0.0, 0.0)
        return (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )

    @staticmethod
    def _add_hotel_marker(itinerary: Itinerary, cluster: MarkerCluster) -> None:
        hotel = itinerary.hotel
        folium.CircleMarker(
            location=(hotel.lat, hotel.lng),
            radius=9,
            popup=folium.Popup(f"<b>{hotel.name}</b><br>{hotel.address}", max_width=250),
            color="#ffffff",
            weight=2,
            fill=True,
            fill_color=HOTEL_MARKER_COLOR,
            fill_opacity=1,
        ).add_to(cluster)

    def _add_day_markers(self, day: DayPlan, cluster: MarkerCluster) -> None:
        color = day_color(day.day_number)
        for item in day.items:
            if item.lat is None or item.lng is None:
                continue
            folium.CircleMarker(
                location=(item.lat, item.lng),
                radius=7,
                popup=folium.Popup(self._popup_html(day, item), max_width=250),
                color=color,
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
            ).add_to(cluster)

    @staticmethod
    def _popup_html(day: DayPlan, item: ItineraryItem) -> str:
        cost = f"<br>${item.cost:.0f}" if item.cost else ""
        return (
            f"<b>Day {day.day_number}</b> ({day.date}): {item.title}"
            f"<br>{item.start_time.time()} &middot; {item.activity_type}{cost}"
        )

    @staticmethod
    def _sorted_points(day: DayPlan) -> list[tuple[float, float]]:
        items = sorted(day.items, key=lambda i: i.start_time)
        return [(i.lat, i.lng) for i in items if i.lat is not None and i.lng is not None]

    def _add_day_route(self, day: DayPlan, fmap: folium.Map) -> None:
        points = self._sorted_points(day)
        if len(points) < 2:
            return
        folium.PolyLine(
            points,
            color=day_color(day.day_number),
            weight=3,
            opacity=0.7,
            tooltip=f"Day {day.day_number} route",
        ).add_to(fmap)

    def _add_timeline(self, itinerary: Itinerary, fmap: folium.Map) -> None:
        features = []
        for day in itinerary.days:
            points = self._sorted_points(day)
            if len(points) < 2:
                continue
            timestamp = f"{day.date.isoformat()}T00:00:00"
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [(lng, lat) for lat, lng in points],
                    },
                    "properties": {
                        "times": [timestamp] * len(points),
                        "style": {"color": day_color(day.day_number), "weight": 4},
                    },
                }
            )
        if not features:
            return
        TimestampedGeoJson(
            {"type": "FeatureCollection", "features": features},
            period="P1D",
            duration=None,
            auto_play=False,
            loop=False,
            add_last_point=False,
        ).add_to(fmap)


def render_thumbnail_png(
    html_path: str | Path,
    png_path: str | Path,
    width: int = 900,
    height: int = 650,
    wait_ms: int = 800,
) -> Path:
    """Screenshots a saved map HTML file with a headless Chromium (Playwright),
    for embedding a static preview in the Week 14 PDF (which can't render live
    Leaflet JS). Requires `playwright install chromium` once per machine.
    """
    from playwright.sync_api import sync_playwright

    html_path = Path(html_path)
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(html_path.resolve().as_uri())
        page.wait_for_timeout(wait_ms)
        page.screenshot(path=str(png_path))
        browser.close()
    return png_path
