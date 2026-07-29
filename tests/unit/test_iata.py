from travel_agent.utils.iata import city_to_iata


def test_exact_match_lowercase():
    assert city_to_iata("paris") == "PAR"


def test_exact_match_case_insensitive():
    assert city_to_iata("PARIS") == "PAR"
    assert city_to_iata("Paris") == "PAR"


def test_exact_match_with_whitespace():
    assert city_to_iata("  london  ") == "LON"


def test_substring_match():
    assert city_to_iata("greater london area") == "LON"


def test_unknown_city_returns_none():
    assert city_to_iata("Nowhereville") is None
