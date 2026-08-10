import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from travel_agent.tools.currency_converter import STATIC_FALLBACK_RATES, CurrencyConverter

RATES_URL = "https://open.er-api.com/v6/latest/USD"


def _tool(fake_cache):
    return CurrencyConverter(cache=fake_cache)


def _mock_rates(rates=None):
    responses.add(
        responses.GET,
        RATES_URL,
        json={"result": "success", "base_code": "USD", "rates": rates or {"EUR": 0.92}},
        status=200,
    )


# --- USD passthrough (no network call needed) --------------------------------


def test_to_usd_is_a_no_op_for_usd():
    tool = CurrencyConverter(cache=None)  # would raise if it ever hit the network
    assert tool.to_usd(100, "USD") == 100


def test_from_usd_is_a_no_op_for_usd():
    tool = CurrencyConverter(cache=None)
    assert tool.from_usd(100, "USD") == 100


def test_currency_code_is_case_insensitive():
    tool = CurrencyConverter(cache=None)
    assert tool.to_usd(100, "usd") == 100


# --- live conversion -----------------------------------------------------


@responses.activate
def test_to_usd_converts_using_live_rate(fake_cache):
    _mock_rates({"EUR": 0.92})
    tool = _tool(fake_cache)
    assert tool.to_usd(92, "EUR") == 100.0


@responses.activate
def test_from_usd_converts_using_live_rate(fake_cache):
    _mock_rates({"EUR": 0.92})
    tool = _tool(fake_cache)
    assert tool.from_usd(100, "EUR") == 92.0


@responses.activate
def test_rates_are_cached_after_first_call(fake_cache):
    _mock_rates({"EUR": 0.92})
    tool = _tool(fake_cache)
    tool.to_usd(92, "EUR")
    tool.to_usd(46, "EUR")  # second call must not hit the network again
    assert len(responses.calls) == 1


# --- graceful degradation -------------------------------------------------


@responses.activate
def test_falls_back_to_static_rates_on_connection_error(fake_cache):
    responses.add(responses.GET, RATES_URL, body=RequestsConnectionError())
    tool = _tool(fake_cache)
    expected = 100 / STATIC_FALLBACK_RATES["EUR"]
    assert tool.to_usd(100, "EUR") == expected


@responses.activate
def test_falls_back_to_static_rates_on_malformed_response(fake_cache):
    responses.add(responses.GET, RATES_URL, json={"unexpected": "shape"}, status=200)
    tool = _tool(fake_cache)
    expected = 100 / STATIC_FALLBACK_RATES["EUR"]
    assert tool.to_usd(100, "EUR") == expected


@responses.activate
def test_unknown_currency_is_treated_as_already_usd(fake_cache):
    _mock_rates({"EUR": 0.92})
    tool = _tool(fake_cache)
    assert tool.to_usd(100, "XXX") == 100
    assert tool.from_usd(100, "XXX") == 100
