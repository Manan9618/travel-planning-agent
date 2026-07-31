"""PDFGenerator — Week 14 deliverable.

Renders a built Itinerary as a professional multi-page PDF via WeasyPrint
(HTML/CSS -> PDF; no headless browser needed here, unlike Week 13's map
thumbnails, since WeasyPrint has its own layout engine): a cover page
(destination photo via Unsplash if configured, else a CSS gradient), an
executive summary, one section per day (reusing Week 13's `day_color` so a
day's PDF section and its map pins/routes share the same color), an embedded
static map thumbnail (Week 13's `render_thumbnail_png`), a QR code linking to
the interactive map (only rendered if a real URL is supplied — there's no
hosted map until Week 15's FastAPI backend exists), and a styled budget
breakdown table (Week 8's `BudgetEvaluation` if available, else just the
estimated total).
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path

import qrcode
import requests
from weasyprint import HTML

from travel_agent.models.core import BudgetEvaluation, DayPlan, Itinerary, ItineraryItem
from travel_agent.tools.budget_tracker import estimate_itinerary_cost
from travel_agent.tools.travel_map_generator import day_color
from travel_agent.tools.unsplash_photo import UnsplashPhotoTool

logger = logging.getLogger(__name__)

PHOTO_DOWNLOAD_TIMEOUT = 10

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
            self._executive_summary(itinerary),
            self._map_section(map_thumbnail_path, map_url),
            *[self._day_section(day) for day in itinerary.days],
            self._budget_section(itinerary, budget_evaluation),
        ]
        return f"<html><head><style>{_CSS}</style></head><body>{''.join(sections)}</body></html>"

    # --- sections -----------------------------------------------------

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
            <h1>{prefs.destination}</h1>
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

    @staticmethod
    def _day_section(day: DayPlan) -> str:
        color = day_color(day.day_number)
        if day.items:
            items_html = "".join(PDFGenerator._item_row(i) for i in day.items)
            items_html = f"<table>{items_html}</table>"
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

    @staticmethod
    def _item_row(item: ItineraryItem) -> str:
        cost = f"${item.cost:,.0f}" if item.cost else ""
        return (
            f"<tr><td>{item.start_time.time().strftime('%H:%M')}</td>"
            f"<td>{item.title}</td><td>{item.activity_type}</td><td>{cost}</td></tr>"
        )

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
