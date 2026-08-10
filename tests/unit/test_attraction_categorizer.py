from travel_agent.tools.attraction_categorizer import (
    _CATEGORY_KEYWORDS,
    DEFAULT_CATEGORY,
    classify_category,
)
from travel_agent.tools.weather_matcher import _INDOOR_KEYWORDS, _OUTDOOR_KEYWORDS


def test_museum_keyword_in_name():
    assert classify_category("Louvre Museum") == "Museum & Gallery"


def test_religious_site_keyword_in_name():
    assert classify_category("Notre-Dame Cathedral") == "Religious Site"


def test_historic_site_keyword_in_name():
    assert classify_category("Edinburgh Castle") == "Historic Site & Monument"


def test_zoo_keyword_in_name():
    assert classify_category("San Diego Zoo") == "Zoo & Wildlife Park"


def test_aquarium_keyword_in_name():
    assert classify_category("National Aquarium") == "Aquarium"


def test_theme_park_keyword_in_name():
    assert classify_category("Magic Kingdom Theme Park") == "Amusement & Theme Park"


def test_entertainment_keyword_in_name():
    assert classify_category("Royal Opera House") == "Entertainment & Nightlife"


def test_shopping_keyword_in_name():
    assert classify_category("Grand Bazaar Market") == "Shopping & Market"


def test_beach_keyword_in_name():
    assert classify_category("Copacabana Beach") == "Beach & Water"


def test_park_keyword_in_name():
    assert classify_category("Central Park") == "Park & Nature"


def test_landmark_keyword_in_name():
    assert classify_category("Tower Bridge") == "Landmark & Viewpoint"


def test_no_keyword_match_falls_back_to_default():
    assert classify_category("Xyzzyplex") == DEFAULT_CATEGORY


def test_generic_source_category_is_ignored_when_name_has_a_signal():
    # The whole point: Serper's own category is "Tourist attraction" for
    # nearly everything, so a real keyword in the name must win over it.
    assert classify_category("Eiffel Tower", raw_category="Tourist attraction") == (
        "Landmark & Viewpoint"
    )


def test_raw_category_is_used_as_a_secondary_signal():
    # A name with no keyword match at all can still be classified from the
    # source's own category when that happens to be more specific.
    assert classify_category("Xyzzyplex", raw_category="History museum") == "Museum & Gallery"


def test_case_insensitive():
    assert classify_category("GRAND MUSEUM") == "Museum & Gallery"


def test_none_raw_category_does_not_raise():
    assert classify_category("Some Place", raw_category=None) == DEFAULT_CATEGORY


# --- weather_matcher interop (Week 22 regression) --------------------------


def test_no_category_label_contains_both_an_indoor_and_outdoor_keyword():
    """Real bug found live: `weather_matcher.classify_setting` re-derives
    indoor/outdoor from `f"{category} {name}".lower()`, checking indoor
    keywords first. A combined "Zoo, Aquarium & Wildlife" label put the
    substring "aquarium" (an indoor keyword there) into the text for every
    zoo too (an outdoor keyword) - silently reclassifying every genuinely
    outdoor zoo as indoor. This asserts no category label this module can
    return could ever inject that kind of conflicting signal, so the same
    class of bug can't reappear as new categories are added."""
    labels = [name for name, _ in _CATEGORY_KEYWORDS] + [DEFAULT_CATEGORY]
    for label in labels:
        text = label.lower()
        indoor_hits = [k for k in _INDOOR_KEYWORDS if k in text]
        outdoor_hits = [k for k in _OUTDOOR_KEYWORDS if k in text]
        assert not (
            indoor_hits and outdoor_hits
        ), f"{label!r} contains both indoor{indoor_hits} and outdoor{outdoor_hits} keywords"
