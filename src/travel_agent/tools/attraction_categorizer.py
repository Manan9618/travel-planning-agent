"""Attraction category classification — Week 22 deliverable.

Real bug traced during Week 12's evaluation and left unfixed until now: Serper's
`/places` endpoint returns the generic category `"Tourist attraction"` for nearly
everything (verified directly against live Paris results), which made
`ItineraryEvaluator._variety` (distinct categories ÷ total attractions) score
2.5/10 on average across all 25 baseline scenarios — not because scheduled trips
actually lacked variety, but because the category data itself carried no signal.

This derives a finer category from the attraction's name (and Serper's own
category as a secondary signal, since it's occasionally more specific than
"Tourist attraction") via keyword matching — the same approach
`weather_matcher.py` already uses for indoor/outdoor classification, applied to
a richer taxonomy. Order matters: checked top-to-bottom, first match wins, so
more specific keywords are listed before more general ones (e.g. "botanical
garden" content matches "Museum" first if it happened to contain "gallery", so
keyword lists are kept mutually exclusive in practice rather than relying on
ordering to break every tie).
"""

from __future__ import annotations

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        "Museum & Gallery",
        ["museum", "gallery", "exhibit", "planetarium", "science center", "art center"],
    ),
    (
        "Religious Site",
        [
            "cathedral",
            "church",
            "basilica",
            "temple",
            "mosque",
            "synagogue",
            "shrine",
            "chapel",
            "monastery",
            "abbey",
        ],
    ),
    (
        "Historic Site & Monument",
        [
            "castle",
            "palace",
            "ruins",
            "monument",
            "memorial",
            "fort",
            "fortress",
            "historic",
            "heritage",
            "archaeological",
        ],
    ),
    # Zoo/wildlife and aquarium are kept as SEPARATE categories rather than
    # one combined label, even though they're conceptually related: a real
    # bug found reviewing this file's own effect on `weather_matcher.py` -
    # that module re-derives indoor/outdoor from `f"{category} {name}"`, and
    # a combined "Zoo, Aquarium & Wildlife" label would put the word
    # "aquarium" (an indoor keyword there) into the text for every zoo too
    # (an outdoor keyword), and indoor is checked first - silently
    # reclassifying every genuinely-outdoor zoo as indoor.
    (
        "Zoo & Wildlife Park",
        ["zoo", "safari", "wildlife", "sanctuary"],
    ),
    (
        "Aquarium",
        ["aquarium"],
    ),
    (
        "Amusement & Theme Park",
        ["theme park", "amusement park", "water park", "roller coaster"],
    ),
    (
        "Entertainment & Nightlife",
        [
            "theatre",
            "theater",
            "opera",
            "casino",
            "nightclub",
            "cinema",
            "concert hall",
            "cabaret",
        ],
    ),
    (
        "Shopping & Market",
        ["market", "mall", "bazaar", "shopping", "souk"],
    ),
    (
        "Beach & Water",
        ["beach", "waterfall", "lake", "river", "harbor", "harbour", "pier", "canal", "lagoon"],
    ),
    (
        "Park & Nature",
        ["park", "garden", "botanical", "nature reserve", "forest", "trail", "hiking"],
    ),
    (
        "Landmark & Viewpoint",
        [
            "tower",
            "bridge",
            "square",
            "plaza",
            "viewpoint",
            "overlook",
            "vista",
            "cliff",
            "canyon",
            "island",
        ],
    ),
]

DEFAULT_CATEGORY = "Landmark & Attraction"


def classify_category(name: str, raw_category: str | None = None) -> str:
    """Best-effort, finer-grained category from an attraction's name (and, as
    a secondary signal, whatever category the data source supplied - useful
    on the rare occasion it's more specific than "Tourist attraction").
    Falls back to `DEFAULT_CATEGORY` rather than the source's generic label,
    so every attraction still contributes a *some* signal to variety scoring
    instead of collapsing the whole set into one bucket.
    """
    text = f"{name} {raw_category or ''}".lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return category
    return DEFAULT_CATEGORY
