"""CurrencyConverter — real exchange rates for non-USD budgets.

Every dollar figure elsewhere in this project (flight/hotel prices from
providers, restaurant/attraction costs, the budget optimizer's and conflict
detector's internal math) is implicitly USD — `TravelPreferences.
budget_currency` has, until now, been a pure display label with no effect
on any comparison. That's a real latent bug for a non-USD budget: a
traveler who says "under €2000" has that 2000 silently treated as if it
were $2000 everywhere the optimizer/conflict detector compares it against
real (USD) costs, understating or overstating their actual budget by
whatever the EUR/USD spread happens to be.

`to_usd`/`from_usd` are the fix, used at the small number of call sites
that compare `budget_total` against real costs (see
`models/core.budget_total_usd`) — deliberately NOT threaded through the
rest of the pipeline (search tools, itinerary builder internals stay
USD-only as before), matching this feature's intentionally light scope.

Uses open.er-api.com (free, no API key required — this project already has
enough required external credentials without adding one more just for
currency) for live rates, Redis-cached like every other external call in
this project to avoid a network round trip per comparison. Falls back to a
small static rate table — approximate, clearly marked, same
graceful-degradation spirit as `HotelSearchTool`'s mock-hotel fallback —
if the live call fails or Redis isn't configured.
"""

from __future__ import annotations

import logging

import requests

from travel_agent.utils.cache import Cache

logger = logging.getLogger(__name__)

_RATES_URL = "https://open.er-api.com/v6/latest/USD"
REQUEST_TIMEOUT = 5
_CACHE_KEY = "currency:usd_rates"
# FX rates don't move fast enough to need fresher than this, and it keeps
# this tool from making a live network call on every single comparison.
_CACHE_TTL_SECONDS = 6 * 60 * 60

# 1 USD = X units of currency. Approximate, updated only when noticed
# stale — a fallback of last resort, not a source of truth. Only currencies
# plausible for this app's "budget_currency" field need to be here; an
# unlisted currency is treated as already-USD (see `to_usd`/`from_usd`)
# rather than raising, consistent with this project's "degrade, don't
# break" stance on every other optional external dependency.
STATIC_FALLBACK_RATES: dict[str, float] = {
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 149.0,
    "INR": 83.0,
    "AUD": 1.52,
    "CAD": 1.36,
    "CHF": 0.88,
    "CNY": 7.24,
    "MXN": 17.0,
    "SGD": 1.34,
}


class CurrencyConverter:
    def __init__(self, cache: Cache | None = None) -> None:
        self._cache = cache or Cache()

    def _rates(self) -> dict[str, float]:
        if cached := self._cache.get(_CACHE_KEY):
            return cached
        try:
            resp = requests.get(_RATES_URL, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            rates = resp.json()["rates"]
        except (requests.RequestException, KeyError, ValueError) as exc:
            logger.warning("Currency rate lookup failed, using static fallback: %s", exc)
            return STATIC_FALLBACK_RATES
        self._cache.set(_CACHE_KEY, rates, _CACHE_TTL_SECONDS)
        return rates

    def to_usd(self, amount: float, currency: str) -> float:
        currency = currency.upper()
        if currency == "USD":
            return amount
        rate = self._rates().get(currency)
        if rate is None:
            logger.warning("No exchange rate for %r, treating amount as already USD", currency)
            return amount
        return amount / rate

    def from_usd(self, amount: float, currency: str) -> float:
        currency = currency.upper()
        if currency == "USD":
            return amount
        rate = self._rates().get(currency)
        if rate is None:
            logger.warning("No exchange rate for %r, returning USD amount unconverted", currency)
            return amount
        return amount * rate
