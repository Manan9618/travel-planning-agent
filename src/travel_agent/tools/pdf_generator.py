"""PDFGenerator — Week 14 deliverable.

Renders a built Itinerary as a professional multi-page PDF via WeasyPrint
(HTML/CSS -> PDF; no headless browser needed here, unlike Week 13's map
thumbnails, since WeasyPrint has its own layout engine): a cover page
(destination photo via Unsplash if configured, else a CSS gradient), an
executive summary, one section per day (reusing Week 13's `day_color` so a
day's PDF section and its map pins/routes share the same color), an embedded
static map thumbnail (Week 13's `render_thumbnail_png`), a QR code linking to
the interactive map (only rendered if a real URL is supplied — there's no
hosted map until Week 15's FastAPI backend exists), a styled budget
breakdown table (Week 8's `BudgetEvaluation` if available, else just the
estimated total), and (post-Week-16) a small Unsplash thumbnail next to each
attraction row, MakeMyTrip-style — e.g. a real Eiffel Tower photo next to an
"Eiffel Tower" item, not just the one destination-level cover photo. Scoped
to `activity_type == "attraction"` only (not restaurants/hotels/transfers)
to keep the extra Unsplash calls bounded; same graceful no-key/no-result
fallback as the cover photo, so a row simply renders without a thumbnail
rather than blocking or breaking the PDF. Also renders a 2-3 sentence
history/why-visit blurb (`item.description`) under the title when present —
both `photo_url` and `description` are normally filled in by the
`enrich_attractions` graph step before the PDF is generated, so this class
reuses them rather than re-fetching; a standalone `PDFGenerator` call (e.g.
in tests) still works, falling back to its own Unsplash lookup for the
photo and simply showing no description.

Visual redesign (post-Week-23), inspired by a printed adventure-camp
brochure the user shared as reference: a colorful "Quick Overview" badge row
(duration/travelers/pace/style/estimated cost), a two-column "Inclusions &
Exclusions" list, and a "Packing Essentials" checklist — all still derived
from the actual planned trip (weather forecasts, trip style, pace, hotel and
flight presence) rather than the fixed copy a real brochure would use, since
this generator has to work for any AI-planned destination, not one curated
package. Icon-style bullets are plain CSS-drawn dots rather than emoji glyphs
— the Docker image only ships `fonts-liberation`, which doesn't reliably
include symbol code points, so dots avoid a tofu-box risk that real pictogram
characters would carry.
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path

import qrcode
import requests
from weasyprint import HTML

from travel_agent.models.core import (
    BudgetEvaluation,
    DayPlan,
    Itinerary,
    ItineraryItem,
    Pace,
    TripStyle,
)
from travel_agent.tools.budget_tracker import estimate_itinerary_cost
from travel_agent.tools.travel_map_generator import day_color
from travel_agent.tools.unsplash_photo import UnsplashPhotoTool

logger = logging.getLogger(__name__)

PHOTO_DOWNLOAD_TIMEOUT = 10

# Quick Overview badges cycle through this palette by position, purely for
# visual variety — no meaning is attached to which stat gets which color.
_BADGE_COLORS = ["#2c5f8a", "#e08a3c", "#1f8a8a", "#7a5cc9", "#2f9e5b", "#c9765c"]

_CSS = """
@page { size: A4; margin: 2cm; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #222; font-size: 11pt; }
h1 { font-size: 32pt; margin: 0; }
h2 { font-size: 16pt; margin: 0 0 0.5em 0; border-left: 6px solid #2c5f8a; padding-left: 0.4em; }
table { width: 100%; border-collapse: collapse; margin-bottom: 1em; }
td, th { padding: 4px 8px; border-bottom: 1px solid #ddd; text-align: left; }
.cover {
  height: 22cm; display: flex; align-items: flex-end; background-size: cover;
  background-position: center; color: white; page-break-after: always;
  background-color: #1a3a5c;
}
.cover-overlay {
  background: linear-gradient(transparent, rgba(0,0,0,0.75)); width: 100%;
  padding: 1.5em; box-sizing: border-box;
}
.cover .subtitle, .cover .trip-style { font-size: 14pt; margin: 0.2em 0 0 0; }
.attribution { font-size: 8pt; color: #888; text-align: right; margin-top: -0.8em; }
.attribution a { color: #888; }
section { page-break-inside: avoid; margin-bottom: 1.5em; }
.day-badge {
  display: inline-block; width: 1.6em; height: 1.6em; border-radius: 50%;
  color: white; text-align: center; line-height: 1.6em; margin-right: 0.4em; font-size: 10pt;
}
.empty { color: #888; font-style: italic; }
.warnings { color: #a05a00; }
.map-thumbnail { width: 100%; border: 1px solid #ddd; }
.qr { text-align: center; margin-top: 0.5em; }
.qr img { width: 3cm; height: 3cm; }
.status-over { color: #b02a2a; font-weight: bold; }
.status-under { color: #2a7a2a; }
.status-on_target { color: #226; }
.item-row {
  display: flex; align-items: center; gap: 0.6em; padding: 6px 0;
  border-bottom: 1px solid #ddd;
}
.item-row:last-child { border-bottom: none; }
.item-thumb {
  width: 3.2cm; height: 2.2cm; object-fit: cover; border-radius: 4px; flex-shrink: 0;
}
.item-main { flex: 1; }
.item-time { color: #888; font-size: 9pt; }
.item-title { font-weight: bold; }
.item-description { color: #555; font-size: 9pt; margin-top: 2px; line-height: 1.35; }
.item-cost { text-align: right; font-weight: bold; white-space: nowrap; }
.badge-row { display: flex; flex-wrap: wrap; gap: 0.5em; }
.badge {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-width: 3.4cm; padding: 0.5em 0.7em; border-radius: 10px; color: white; text-align: center;
}
.badge .badge-value { font-size: 13pt; font-weight: bold; line-height: 1.2; }
.badge .badge-label {
  font-size: 8pt; text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.9;
}
.inclusion-exclusion h2 { border-left-color: #2f9e5b; }
.packing h2 { border-left-color: #1f8a8a; }
h3 { font-size: 11pt; margin: 0.6em 0 0.3em 0; }
.two-col { display: flex; gap: 1.5em; }
.two-col > div { flex: 1; }
.dot-list { list-style: none; margin: 0; padding: 0; }
.dot-list li { display: flex; align-items: flex-start; gap: 0.5em; padding: 3px 0; }
.dot-list.two-col-list { display: flex; flex-wrap: wrap; }
.dot-list.two-col-list li { width: 50%; box-sizing: border-box; padding-right: 0.5em; }
.dot {
  display: inline-block; width: 0.65em; height: 0.65em; border-radius: 50%;
  margin-top: 0.4em; flex-shrink: 0;
}
.dot-included { background: #2f9e5b; }
.dot-excluded { background: #c94f4f; }
.dot-packing { background: #1f8a8a; }
.footer-band {
  margin-top: 2em; padding: 1em 1.5em; border-radius: 8px; text-align: center; color: white;
  background: linear-gradient(135deg, #2c5f8a, #1f8a8a);
}
.footer-band .tagline { font-size: 13pt; font-weight: bold; margin: 0 0 0.2em 0; }
.footer-band .subtext { font-size: 9pt; opacity: 0.85; margin: 0; }
"""


class PDFGenerator:
    def __init__(self, photo_tool: UnsplashPhotoTool | None = None) -> None:
        self._photo_tool = photo_tool or UnsplashPhotoTool()

    def generate(
        self,
        itinerary: Itinerary,
        output_path: str | Path,
        budget_evaluation: BudgetEvaluation | None = None,
        map_thumbnail_path: str | Path | None = None,
        map_url: str | None = None,
    ) -> Path:
        html = self.render_html(itinerary, budget_evaluation, map_thumbnail_path, map_url)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        HTML(string=html).write_pdf(str(output_path))
        return output_path

    def render_html(
        self,
        itinerary: Itinerary,
        budget_evaluation: BudgetEvaluation | None = None,
        map_thumbnail_path: str | Path | None = None,
        map_url: str | None = None,
    ) -> str:
        sections = [
            self._cover_page(itinerary),
            self._quick_overview_section(itinerary),
            self._executive_summary(itinerary),
            self._inclusion_exclusion_section(itinerary),
            self._map_section(map_thumbnail_path, map_url),
            *[self._day_section(day, itinerary.preferences.destination) for day in itinerary.days],
            self._packing_essentials_section(itinerary),
            self._budget_section(itinerary, budget_evaluation),
            self._footer_section(),
        ]
        return f"<html><head><style>{_CSS}</style></head><body>{''.join(sections)}</body></html>"

    # --- sections -----------------------------------------------------

    @staticmethod
    def _destination_label(prefs) -> str:
        destinations = [prefs.destination, *prefs.additional_destinations]
        if len(destinations) == 1:
            return destinations[0]
        if len(destinations) == 2:
            return " & ".join(destinations)
        return ", ".join(destinations[:-1]) + f" & {destinations[-1]}"

    def _cover_page(self, itinerary: Itinerary) -> str:
        prefs = itinerary.preferences
        photo = self._photo_tool.get_cover_photo(prefs.destination)
        background_style = ""
        attribution = ""
        if photo:
            image_b64 = self._download_as_base64(photo.url)
            if image_b64:
                background_style = f"background-image: url(data:image/jpeg;base64,{image_b64});"
                attribution = (
                    f'<p class="attribution">Photo by '
                    f'<a href="{photo.photographer_url}">{photo.photographer_name}</a> '
                    f"on Unsplash</p>"
                )

        dates = ""
        if prefs.start_date and prefs.end_date:
            dates = (
                f"{prefs.start_date.strftime('%b %d')} - " f"{prefs.end_date.strftime('%b %d, %Y')}"
            )
        trip_style = (
            f'<p class="trip-style">{prefs.trip_style.value.replace("_", " ").title()} trip</p>'
            if prefs.trip_style
            else ""
        )
        return f"""
        <section class="cover" style="{background_style}">
          <div class="cover-overlay">
            <h1>{self._destination_label(prefs)}</h1>
            <p class="subtitle">{dates}</p>
            {trip_style}
          </div>
        </section>
        {attribution}
        """

    @staticmethod
    def _download_as_base64(url: str) -> str | None:
        try:
            resp = requests.get(url, timeout=PHOTO_DOWNLOAD_TIMEOUT)
            resp.raise_for_status()
            return base64.b64encode(resp.content).decode("ascii")
        except requests.RequestException as exc:
            logger.warning("Failed to download cover photo: %s", exc)
            return None

    @staticmethod
    def _executive_summary(itinerary: Itinerary) -> str:
        prefs = itinerary.preferences
        num_days = len(itinerary.days)
        num_attractions = sum(
            1 for d in itinerary.days for i in d.items if i.activity_type == "attraction"
        )
        num_restaurants = sum(
            1 for d in itinerary.days for i in d.items if i.activity_type == "restaurant"
        )
        total_cost = estimate_itinerary_cost(itinerary)

        rows = [
            ("Duration", f"{num_days} day{'s' if num_days != 1 else ''}"),
            ("Travelers", str(prefs.travelers)),
            ("Attractions", str(num_attractions)),
            ("Restaurants", str(num_restaurants)),
            ("Estimated total cost", f"${total_cost:,.0f}"),
        ]
        if prefs.budget_total:
            rows.append(("Stated budget", f"${prefs.budget_total:,.0f} {prefs.budget_currency}"))
        if prefs.must_see:
            rows.append(("Must-see", ", ".join(prefs.must_see)))
        if prefs.interests:
            rows.append(("Interests", ", ".join(prefs.interests)))

        row_html = "".join(f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in rows)
        return f'<section class="summary"><h2>Trip Overview</h2><table>{row_html}</table></section>'

    @staticmethod
    def _quick_overview_section(itinerary: Itinerary) -> str:
        prefs = itinerary.preferences
        num_days = len(itinerary.days)
        total_cost = estimate_itinerary_cost(itinerary)

        stats = [
            ("Duration", f"{num_days} day{'s' if num_days != 1 else ''}"),
            ("Travelers", str(prefs.travelers)),
            ("Pace", prefs.pace.value.title()),
        ]
        if prefs.trip_style:
            stats.append(("Style", prefs.trip_style.value.replace("_", " ").title()))
        if prefs.budget_tier:
            stats.append(("Budget tier", prefs.budget_tier.value.replace("_", " ").title()))
        stats.append(("Est. cost", f"${total_cost:,.0f}"))

        badges_html = "".join(
            f'<div class="badge" style="background:{_BADGE_COLORS[i % len(_BADGE_COLORS)]}">'
            f'<span class="badge-value">{value}</span>'
            f'<span class="badge-label">{label}</span></div>'
            for i, (label, value) in enumerate(stats)
        )
        return (
            f'<section class="quick-overview"><div class="badge-row">{badges_html}</div></section>'
        )

    @staticmethod
    def _inclusion_exclusion_section(itinerary: Itinerary) -> str:
        included = ["Full day-by-day itinerary & route map"]
        if itinerary.hotel:
            included.append(f"Accommodation: {itinerary.hotel.name}")
        if itinerary.flights:
            included.append("Round-trip flights")
        num_attractions = sum(
            1 for d in itinerary.days for i in d.items if i.activity_type == "attraction"
        )
        if num_attractions:
            included.append(
                f"{num_attractions} attraction visit{'s' if num_attractions != 1 else ''}"
            )
        num_restaurants = sum(
            1 for d in itinerary.days for i in d.items if i.activity_type == "restaurant"
        )
        if num_restaurants:
            included.append(
                f"{num_restaurants} dining recommendation{'s' if num_restaurants != 1 else ''}"
            )

        excluded = [
            "Personal expenses & shopping",
            "Travel insurance",
            "Visa & passport fees",
            "Tips & gratuities",
        ]

        def _dot_list(items: list[str], dot_class: str) -> str:
            return "".join(
                f'<li><span class="dot {dot_class}"></span>{item}</li>' for item in items
            )

        included_html = _dot_list(included, "dot-included")
        excluded_html = _dot_list(excluded, "dot-excluded")
        return f"""
        <section class="inclusion-exclusion">
          <h2>Inclusions &amp; Exclusions</h2>
          <div class="two-col">
            <div><h3>Included</h3><ul class="dot-list">{included_html}</ul></div>
            <div><h3>Not Included</h3><ul class="dot-list">{excluded_html}</ul></div>
          </div>
        </section>
        """

    @staticmethod
    def _packing_essentials_section(itinerary: Itinerary) -> str:
        prefs = itinerary.preferences
        forecasts = [d.weather for d in itinerary.days if d.weather]

        items = [
            "Comfortable walking shoes",
            "Phone charger & travel adapter",
            "Valid ID / passport",
        ]
        if any(f.rain_probability >= 0.4 for f in forecasts):
            items.append("Rain jacket or compact umbrella")
        if any(f.temp_low_c < 12 for f in forecasts):
            items.append("Warm layers / light jacket")
        if any(f.temp_high_c > 28 for f in forecasts):
            items.append("Sunscreen & sunglasses")
            items.append("Light, breathable clothing")
        if prefs.trip_style == TripStyle.BEACH:
            items.append("Swimwear & beach towel")
        if prefs.trip_style == TripStyle.ADVENTURE:
            items.append("Daypack & basic first-aid kit")
        if prefs.pace == Pace.PACKED:
            items.append("Portable battery pack — long days ahead")
        if prefs.dietary_restrictions:
            items.append(f"Dietary needs to flag: {', '.join(prefs.dietary_restrictions)}")

        items_html = "".join(f'<li><span class="dot dot-packing"></span>{i}</li>' for i in items)
        return (
            '<section class="packing"><h2>Packing Essentials</h2>'
            f'<ul class="dot-list two-col-list">{items_html}</ul></section>'
        )

    @staticmethod
    def _footer_section() -> str:
        return """
        <section class="footer-band">
          <p class="tagline">Have an amazing trip!</p>
          <p class="subtext">Crafted by Waypoint &mdash; your AI travel planning agent</p>
        </section>
        """

    @staticmethod
    def _map_section(map_thumbnail_path: str | Path | None, map_url: str | None) -> str:
        if not map_thumbnail_path:
            return ""
        path = Path(map_thumbnail_path)
        if not path.exists():
            return ""
        image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")

        qr_html = ""
        if map_url:
            qr_b64 = PDFGenerator._qr_code_base64(map_url)
            qr_html = (
                f'<div class="qr"><img src="data:image/png;base64,{qr_b64}"/>'
                f"<p>Scan for the interactive map</p></div>"
            )
        return (
            f'<section class="map"><h2>Route Map</h2>'
            f'<img class="map-thumbnail" src="data:image/png;base64,{image_b64}"/>'
            f"{qr_html}</section>"
        )

    @staticmethod
    def _qr_code_base64(url: str) -> str:
        img = qrcode.make(url)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _day_section(self, day: DayPlan, destination: str) -> str:
        color = day_color(day.day_number)
        if day.items:
            items_html = "".join(self._item_row(i, destination) for i in day.items)
        else:
            items_html = '<p class="empty">Free day &mdash; nothing scheduled</p>'
        warnings_html = ""
        if day.warnings:
            warnings_html = (
                "<ul class='warnings'>" + "".join(f"<li>{w}</li>" for w in day.warnings) + "</ul>"
            )
        return f"""
        <section class="day">
          <h2 style="border-left-color: {color}">
            <span class="day-badge" style="background: {color}">{day.day_number}</span>
            Day {day.day_number} &middot; {day.date.strftime('%A, %b %d')}
          </h2>
          {items_html}
          {warnings_html}
        </section>
        """

    def _item_row(self, item: ItineraryItem, destination: str) -> str:
        cost = f"${item.cost:,.0f}" if item.cost else ""
        thumb_html = ""
        description_html = ""
        if item.activity_type == "attraction":
            # `photo_url` is set by the `enrich_attractions` graph step when this
            # itinerary came from a real planning run; standalone PDFGenerator
            # usage (e.g. tests) falls back to a direct lookup here.
            photo_url = item.photo_url
            if not photo_url:
                photo = self._photo_tool.get_photo(f"{item.title} {destination}", thumbnail=True)
                photo_url = photo.url if photo else None
            if photo_url:
                image_b64 = self._download_as_base64(photo_url)
                if image_b64:
                    thumb_html = (
                        f'<img class="item-thumb" src="data:image/jpeg;base64,{image_b64}"/>'
                    )
            if item.description:
                description_html = f'<div class="item-description">{item.description}</div>'
        time_str = item.start_time.time().strftime("%H:%M")
        return f"""
        <div class="item-row">
          {thumb_html}
          <div class="item-main">
            <div class="item-time">{time_str} &middot; {item.activity_type}</div>
            <div class="item-title">{item.title}</div>
            {description_html}
          </div>
          <div class="item-cost">{cost}</div>
        </div>
        """

    @staticmethod
    def _budget_section(itinerary: Itinerary, budget_evaluation: BudgetEvaluation | None) -> str:
        if budget_evaluation is None:
            total = estimate_itinerary_cost(itinerary)
            return (
                '<section class="budget"><h2>Budget</h2>'
                f"<p>Estimated total cost: <b>${total:,.0f}</b></p></section>"
            )

        rows = "".join(
            f"<tr><td>{cat.category.title()}</td><td>${cat.allocated:,.0f}</td>"
            f"<td>${cat.actual:,.0f}</td>"
            f"<td class='status-{cat.status}'>{cat.status.replace('_', ' ').title()}</td></tr>"
            for cat in budget_evaluation.categories
        )
        adherence = (
            f"{budget_evaluation.adherence_score:.0%}"
            if budget_evaluation.adherence_score is not None
            else "n/a"
        )
        suggestions_html = ""
        if budget_evaluation.suggestions:
            suggestions_html = (
                "<ul>" + "".join(f"<li>{s}</li>" for s in budget_evaluation.suggestions) + "</ul>"
            )
        return f"""
        <section class="budget">
          <h2>Budget</h2>
          <table>
            <tr><th>Category</th><th>Allocated</th><th>Actual</th><th>Status</th></tr>
            {rows}
          </table>
          <p>Total: <b>${budget_evaluation.total_actual:,.0f}</b> of
             ${budget_evaluation.total_allocated:,.0f} allocated
             (budget adherence: <b>{adherence}</b>)</p>
          {suggestions_html}
        </section>
        """
