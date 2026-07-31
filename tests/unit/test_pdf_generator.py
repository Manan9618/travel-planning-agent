from datetime import date

from pypdf import PdfReader

from travel_agent.models.core import (
    BudgetAllocation,
    BudgetEvaluation,
    CategoryEvaluation,
    DayPlan,
    HotelOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
)
from travel_agent.tools.pdf_generator import PDFGenerator
from travel_agent.tools.unsplash_photo import CoverPhoto


class NoPhotoTool:
    def get_cover_photo(self, destination):
        return None


class FakePhotoTool:
    def __init__(self, photo):
        self._photo = photo

    def get_cover_photo(self, destination):
        return self._photo


def _prefs(**overrides):
    defaults = dict(
        destination="Paris",
        start_date=date(2026, 9, 1),
        duration_days=3,
        raw_text="t",
    )
    defaults.update(overrides)
    return TravelPreferences(**defaults)


def _hotel():
    return HotelOption(
        name="Test Hotel", address="Paris, France", lat=48.85, lng=2.35, price_per_night=100
    )


def _item(title, activity_type="attraction", start="2026-09-02T09:00:00", cost=None):
    return ItineraryItem(
        time_slot="morning",
        start_time=start,
        end_time=start,
        activity_type=activity_type,
        title=title,
        cost=cost,
    )


def _itinerary(days=None, **prefs_overrides):
    days = days if days is not None else [DayPlan(day_number=1, date=date(2026, 9, 1), items=[])]
    return Itinerary(preferences=_prefs(**prefs_overrides), days=days, hotel=_hotel())


def _generator(photo=None):
    return PDFGenerator(photo_tool=NoPhotoTool() if photo is None else FakePhotoTool(photo))


def _extract_text(pdf_path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() for page in reader.pages)


# --- generate() produces a real, valid PDF ----------------------------------


def test_generate_writes_a_valid_pdf(tmp_path):
    out_path = tmp_path / "nested" / "trip.pdf"
    result = _generator().generate(_itinerary(), out_path)
    assert result == out_path
    assert out_path.exists()
    with open(out_path, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_generated_pdf_has_at_least_two_pages(tmp_path):
    out_path = tmp_path / "trip.pdf"
    _generator().generate(_itinerary(), out_path)
    reader = PdfReader(str(out_path))
    assert len(reader.pages) >= 2  # cover + content


# --- cover page -------------------------------------------------------------


def test_cover_page_shows_destination_and_dates():
    itinerary = _itinerary()
    html = _generator().render_html(itinerary)
    assert "<h1>Paris</h1>" in html
    assert "Sep 01" in html


def test_cover_page_falls_back_to_gradient_without_a_photo():
    html = _generator(photo=None).render_html(_itinerary())
    assert "background-image" not in html


def test_cover_page_uses_photo_background_when_available(monkeypatch):
    photo = CoverPhoto(
        url="https://images.unsplash.com/photo-1",
        photographer_name="Jane Doe",
        photographer_url="https://unsplash.com/@jane",
    )
    generator = _generator(photo=photo)
    monkeypatch.setattr(generator, "_download_as_base64", staticmethod(lambda url: "ZmFrZWJ5dGVz"))
    html = generator.render_html(_itinerary())
    assert "background-image: url(data:image/jpeg;base64,ZmFrZWJ5dGVz)" in html
    assert "Jane Doe" in html
    assert "unsplash.com/@jane" in html


def test_cover_falls_back_to_gradient_when_photo_download_fails(monkeypatch):
    photo = CoverPhoto(url="https://x", photographer_name="Jane", photographer_url="https://x")
    generator = _generator(photo=photo)
    monkeypatch.setattr(generator, "_download_as_base64", staticmethod(lambda url: None))
    html = generator.render_html(_itinerary())
    assert "background-image" not in html
    assert "Jane" not in html  # no attribution line without a successful download


# --- executive summary -------------------------------------------------------


def test_executive_summary_lists_key_stats(tmp_path):
    day = DayPlan(
        day_number=2,
        date=date(2026, 9, 2),
        items=[_item("Louvre"), _item("Bistro", activity_type="restaurant", cost=30)],
    )
    itinerary = _itinerary(
        days=[DayPlan(day_number=1, date=date(2026, 9, 1), items=[]), day],
        budget_total=1500,
        must_see=["Louvre"],
        interests=["art"],
    )
    text = _generator().render_html(itinerary)
    assert "Attractions" in text
    assert "Restaurants" in text
    assert "$1,500" in text
    assert "Louvre" in text
    assert "art" in text


# --- day sections -------------------------------------------------------------


def test_day_with_no_items_shows_free_day_message():
    itinerary = _itinerary(days=[DayPlan(day_number=1, date=date(2026, 9, 1), items=[])])
    html = _generator().render_html(itinerary)
    assert "Free day" in html


def test_day_items_rendered_with_time_title_cost():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("Eiffel Tower", cost=25)])
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert "Eiffel Tower" in html
    assert "09:00" in html
    assert "$25" in html


def test_day_badge_color_matches_travel_map_generator_day_color():
    from travel_agent.tools.travel_map_generator import day_color

    day = DayPlan(day_number=2, date=date(2026, 9, 2), items=[])
    itinerary = _itinerary(days=[DayPlan(day_number=1, date=date(2026, 9, 1), items=[]), day])
    html = _generator().render_html(itinerary)
    assert f"background: {day_color(2)}" in html


def test_day_warnings_are_rendered():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[], warnings=["Pack rain gear"])
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert "Pack rain gear" in html


# --- map section -------------------------------------------------------------


def test_no_map_section_when_no_thumbnail_given():
    html = _generator().render_html(_itinerary())
    assert "Route Map" not in html


def test_map_section_included_when_thumbnail_exists(tmp_path):
    png_path = tmp_path / "thumb.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\nfakepngbytes")
    html = _generator().render_html(_itinerary(), map_thumbnail_path=png_path)
    assert "Route Map" in html
    assert "data:image/png;base64," in html


def test_map_section_skipped_when_thumbnail_path_does_not_exist(tmp_path):
    html = _generator().render_html(_itinerary(), map_thumbnail_path=tmp_path / "missing.png")
    assert "Route Map" not in html


def test_qr_code_included_only_when_map_url_given(tmp_path):
    png_path = tmp_path / "thumb.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\nfakepngbytes")

    without_url = _generator().render_html(_itinerary(), map_thumbnail_path=png_path)
    assert "Scan for the interactive map" not in without_url

    with_url = _generator().render_html(
        _itinerary(), map_thumbnail_path=png_path, map_url="https://example.com/map/1"
    )
    assert "Scan for the interactive map" in with_url


# --- budget section -------------------------------------------------------------


def test_budget_section_shows_estimated_total_without_evaluation():
    html = _generator().render_html(_itinerary())
    assert "Estimated total cost" in html


def test_budget_section_shows_category_table_with_evaluation():
    evaluation = BudgetEvaluation(
        allocation=BudgetAllocation(flights=0, hotel=200, food=100, activities=100),
        categories=[
            CategoryEvaluation(
                category="hotel", allocated=200, actual=200, difference=0, status="on_target"
            ),
            CategoryEvaluation(
                category="activities", allocated=100, actual=150, difference=50, status="over"
            ),
        ],
        total_allocated=400,
        total_actual=350,
        adherence_score=0.8,
        suggestions=["Activities is $50 over its $100 budget"],
    )
    html = _generator().render_html(_itinerary(), budget_evaluation=evaluation)
    assert "Hotel" in html
    assert "Activities" in html
    assert "Over" in html
    assert "80%" in html
    assert "$50 over" in html


# --- end-to-end pypdf content verification -----------------------------------


def test_generated_pdf_text_contains_destination_and_day_data(tmp_path):
    day = DayPlan(day_number=2, date=date(2026, 9, 2), items=[_item("Louvre Museum", cost=20)])
    itinerary = _itinerary(
        days=[DayPlan(day_number=1, date=date(2026, 9, 1), items=[]), day], budget_total=1500
    )
    out_path = tmp_path / "trip.pdf"
    _generator().generate(itinerary, out_path)
    text = _extract_text(out_path)
    assert "Paris" in text
    assert "Louvre Museum" in text
    assert "$20" in text
    assert "$1,500" in text
