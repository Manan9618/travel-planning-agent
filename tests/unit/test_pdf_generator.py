from datetime import date

from pypdf import PdfReader

from travel_agent.models.core import (
    BudgetAllocation,
    BudgetEvaluation,
    CategoryEvaluation,
    DayPlan,
    FlightOption,
    HotelOption,
    Itinerary,
    ItineraryItem,
    TravelPreferences,
    WeatherForecast,
)
from travel_agent.tools.pdf_generator import PDFGenerator
from travel_agent.tools.unsplash_photo import CoverPhoto


class NoPhotoTool:
    def get_cover_photo(self, destination):
        return None

    def get_photo(self, query, thumbnail=False):
        return None


class FakePhotoTool:
    def __init__(self, photo):
        self._photo = photo

    def get_cover_photo(self, destination):
        return self._photo

    def get_photo(self, query, thumbnail=False):
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


def _item(
    title,
    activity_type="attraction",
    start="2026-09-02T09:00:00",
    cost=None,
    photo_url=None,
    description=None,
):
    return ItineraryItem(
        time_slot="morning",
        start_time=start,
        end_time=start,
        activity_type=activity_type,
        title=title,
        cost=cost,
        photo_url=photo_url,
        description=description,
    )


def _flight():
    return FlightOption(
        airline="AF",
        origin="JFK",
        destination="CDG",
        departure_time="2026-09-01T09:00:00",
        arrival_time="2026-09-01T21:00:00",
        duration_minutes=420,
        price=650,
    )


def _weather(day_num=1, rain_probability=0.1, temp_low_c=18, temp_high_c=24):
    return WeatherForecast(
        day=date(2026, 9, day_num),
        condition="clear",
        temp_high_c=temp_high_c,
        temp_low_c=temp_low_c,
        rain_probability=rain_probability,
        wind_speed_kph=10,
        comfort_score=8,
    )


def _itinerary(days=None, flights=None, hotel=True, **prefs_overrides):
    days = days if days is not None else [DayPlan(day_number=1, date=date(2026, 9, 1), items=[])]
    return Itinerary(
        preferences=_prefs(**prefs_overrides),
        days=days,
        flights=flights or [],
        hotel=_hotel() if hotel else None,
    )


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


# --- per-attraction thumbnails -------------------------------------------------


def test_attraction_row_shows_photo_thumbnail_when_available(monkeypatch):
    photo = CoverPhoto(
        url="https://images.unsplash.com/photo-eiffel",
        photographer_name="Jane Doe",
        photographer_url="https://unsplash.com/@jane",
    )
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("Eiffel Tower")])
    itinerary = _itinerary(days=[day])
    generator = _generator(photo=photo)
    monkeypatch.setattr(generator, "_download_as_base64", staticmethod(lambda url: "ZmFrZWJ5dGVz"))
    html = generator.render_html(itinerary)
    assert 'class="item-thumb" src="data:image/jpeg;base64,ZmFrZWJ5dGVz"' in html


def test_attraction_row_has_no_thumbnail_without_a_photo():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("Eiffel Tower")])
    itinerary = _itinerary(days=[day])
    html = _generator(photo=None).render_html(itinerary)
    assert '<img class="item-thumb"' not in html


def test_non_attraction_rows_never_get_a_thumbnail(monkeypatch):
    photo = CoverPhoto(url="https://x", photographer_name="Jane", photographer_url="https://x")
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("Bistro", activity_type="restaurant", cost=30)],
    )
    itinerary = _itinerary(days=[day])
    generator = _generator(photo=photo)
    monkeypatch.setattr(generator, "_download_as_base64", staticmethod(lambda url: "ZmFrZWJ5dGVz"))
    html = generator.render_html(itinerary)
    assert '<img class="item-thumb"' not in html


def test_attraction_thumbnail_lookup_queries_title_and_destination():
    seen_queries = []

    class RecordingPhotoTool:
        def get_cover_photo(self, destination):
            return None

        def get_photo(self, query, thumbnail=False):
            seen_queries.append((query, thumbnail))
            return None

    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("Eiffel Tower")])
    itinerary = _itinerary(days=[day])
    PDFGenerator(photo_tool=RecordingPhotoTool()).render_html(itinerary)
    assert ("Eiffel Tower Paris", True) in seen_queries


def test_attraction_row_reuses_existing_photo_url_without_a_lookup(monkeypatch):
    class RaisingPhotoTool:
        def get_cover_photo(self, destination):
            return None

        def get_photo(self, query, thumbnail=False):
            raise AssertionError("should not look up a photo when photo_url is already set")

    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("Eiffel Tower", photo_url="https://images.unsplash.com/preset-eiffel")],
    )
    itinerary = _itinerary(days=[day])
    generator = PDFGenerator(photo_tool=RaisingPhotoTool())
    monkeypatch.setattr(generator, "_download_as_base64", staticmethod(lambda url: "ZmFrZWJ5dGVz"))
    html = generator.render_html(itinerary)
    assert 'class="item-thumb" src="data:image/jpeg;base64,ZmFrZWJ5dGVz"' in html


def test_attraction_row_shows_description_when_present():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("Eiffel Tower", description="An iconic iron lattice tower in Paris.")],
    )
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert '<div class="item-description">An iconic iron lattice tower in Paris.</div>' in html


def test_attraction_row_has_no_description_div_when_absent():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("Eiffel Tower")])
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert '<div class="item-description">' not in html


def test_non_attraction_rows_never_get_a_description():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[
            _item(
                "Bistro",
                activity_type="restaurant",
                cost=30,
                description="This should never be rendered",
            )
        ],
    )
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert '<div class="item-description">' not in html


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


# --- quick overview badges ----------------------------------------------------


def test_quick_overview_shows_duration_travelers_and_cost():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("Louvre", cost=20)])
    itinerary = _itinerary(days=[day], travelers=2)
    html = _generator().render_html(itinerary)
    assert "1 day" in html
    assert 'class="badge-value">2</span><span class="badge-label">Travelers' in html
    assert "Est. cost" in html


def test_quick_overview_includes_trip_style_and_budget_tier_when_set():
    from travel_agent.models.core import BudgetTier, TripStyle

    itinerary = _itinerary(trip_style=TripStyle.BEACH, budget_tier=BudgetTier.LUXURY)
    html = _generator().render_html(itinerary)
    assert "Beach" in html
    assert "Luxury" in html


def test_quick_overview_omits_style_and_tier_when_unset():
    itinerary = _itinerary()
    html = _generator().render_html(itinerary)
    assert '<span class="badge-label">Style</span>' not in html
    assert '<span class="badge-label">Budget tier</span>' not in html


# --- inclusions & exclusions --------------------------------------------------


def test_inclusion_list_reflects_hotel_and_flights_when_present():
    itinerary = _itinerary(flights=[_flight()], hotel=True)
    html = _generator().render_html(itinerary)
    assert "Accommodation: Test Hotel" in html
    assert "Round-trip flights" in html


def test_inclusion_list_omits_hotel_and_flights_when_absent():
    itinerary = _itinerary(flights=[], hotel=False)
    html = _generator().render_html(itinerary)
    assert "Accommodation:" not in html
    assert "Round-trip flights" not in html


def test_inclusion_list_counts_attractions_and_restaurants():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("Louvre"), _item("Bistro", activity_type="restaurant", cost=30)],
    )
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert "1 attraction visit" in html
    assert "1 dining recommendation" in html


def test_exclusion_list_is_always_present():
    html = _generator().render_html(_itinerary())
    assert "Travel insurance" in html
    assert "Visa & passport fees" in html


# --- packing essentials --------------------------------------------------------


def test_packing_essentials_always_includes_the_baseline_items():
    html = _generator().render_html(_itinerary())
    assert "Comfortable walking shoes" in html


def test_packing_essentials_includes_rain_gear_when_rain_is_likely():
    day = DayPlan(
        day_number=1, date=date(2026, 9, 1), items=[], weather=_weather(rain_probability=0.7)
    )
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert "Rain jacket" in html


def test_packing_essentials_omits_rain_gear_when_dry():
    day = DayPlan(
        day_number=1, date=date(2026, 9, 1), items=[], weather=_weather(rain_probability=0.1)
    )
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert "Rain jacket" not in html


def test_packing_essentials_includes_warm_layers_when_cold():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[], weather=_weather(temp_low_c=2))
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert "Warm layers" in html


def test_packing_essentials_includes_sun_protection_when_hot():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[], weather=_weather(temp_high_c=34))
    itinerary = _itinerary(days=[day])
    html = _generator().render_html(itinerary)
    assert "Sunscreen" in html


def test_packing_essentials_includes_swimwear_for_beach_trips():
    from travel_agent.models.core import TripStyle

    itinerary = _itinerary(trip_style=TripStyle.BEACH)
    html = _generator().render_html(itinerary)
    assert "Swimwear" in html


def test_packing_essentials_includes_first_aid_for_adventure_trips():
    from travel_agent.models.core import TripStyle

    itinerary = _itinerary(trip_style=TripStyle.ADVENTURE)
    html = _generator().render_html(itinerary)
    assert "first-aid" in html


def test_packing_essentials_flags_dietary_restrictions():
    itinerary = _itinerary(dietary_restrictions=["vegan", "nut allergy"])
    html = _generator().render_html(itinerary)
    assert "vegan" in html
    assert "nut allergy" in html


# --- footer ---------------------------------------------------------------


def test_footer_band_is_present():
    html = _generator().render_html(_itinerary())
    assert "Have an amazing trip!" in html
    assert "Waypoint" in html
