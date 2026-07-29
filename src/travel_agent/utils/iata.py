"""Minimal city-name -> IATA code lookup for FlightSearchTool.

TravelPreferences.origin/destination are free-text city names extracted by
PreferenceParser (e.g. "Boston"), but TravelPayouts' flight endpoints need IATA
codes. This is a small static table covering major cities for demo purposes, not a
real geocoding/airport database. Cities outside this table return None, and the
caller should skip flight search rather than guess a wrong code.
"""

from __future__ import annotations

_CITY_TO_IATA: dict[str, str] = {
    "london": "LON",
    "paris": "PAR",
    "new york": "NYC",
    "boston": "BOS",
    "tokyo": "TYO",
    "los angeles": "LAX",
    "san francisco": "SFO",
    "chicago": "CHI",
    "miami": "MIA",
    "rome": "ROM",
    "barcelona": "BCN",
    "madrid": "MAD",
    "berlin": "BER",
    "amsterdam": "AMS",
    "dubai": "DXB",
    "singapore": "SIN",
    "hong kong": "HKG",
    "sydney": "SYD",
    "toronto": "YTO",
    "washington": "WAS",
    "seattle": "SEA",
    "bangkok": "BKK",
    "istanbul": "IST",
    "cairo": "CAI",
    "mumbai": "BOM",
    "delhi": "DEL",
    "beijing": "BJS",
    "shanghai": "SHA",
    "seoul": "SEL",
    "mexico city": "MEX",
    "sao paulo": "SAO",
    "buenos aires": "BUE",
    "moscow": "MOW",
    "vienna": "VIE",
    "zurich": "ZRH",
    "dublin": "DUB",
    "lisbon": "LIS",
    "athens": "ATH",
    "prague": "PRG",
    "copenhagen": "CPH",
    "stockholm": "STO",
    "oslo": "OSL",
    "helsinki": "HEL",
}


def city_to_iata(name: str) -> str | None:
    key = name.strip().lower()
    if key in _CITY_TO_IATA:
        return _CITY_TO_IATA[key]
    for city, code in _CITY_TO_IATA.items():
        if city in key or key in city:
            return code
    return None
