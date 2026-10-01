"""Map a principal-office city to Polk, Dallas, or Warren County.

Split cities stay unresolved. A registered-agent city is never used here.
"""

from __future__ import annotations

POLK = {
    "des moines",
    "ankeny",
    "altoona",
    "pleasant hill",
    "bondurant",
    "johnston",
    "windsor heights",
    "polk city",
    "elkhart",
    "alleman",
    "runnells",
    "mitchellville",
    "saylorville",
    "berwick",
}

DALLAS = {
    "waukee",
    "adel",
    "perry",
    "dallas center",
    "woodward",
    "dexter",
    "redfield",
    "van meter",
    "de soto",
    "minburn",
    "bouton",
    "dawson",
    "linden",
}

WARREN = {
    "indianola",
    "norwalk",
    "hartford",
    "milo",
    "lacona",
    "new virginia",
    "martensdale",
    "cumming",
    "st marys",
    "ackworth",
    "sandyville",
    "spring hill",
}

# Incorporated places that cross one of these county lines.
SPLIT = {
    "west des moines",
    "clive",
    "grimes",
    "urbandale",
    "carlisle",
    "granger",
    "sheldahl",
}


def _norm_city(city: str) -> str:
    text = " ".join(city.lower().replace(".", "").replace("'", "").split())
    return text


def county_for_principal_city(city: str) -> tuple[str, str]:
    """Return (county or blank, basis).

    basis is unique_city, split_city_unresolved, or unknown.
    """
    key = _norm_city(city)
    if key == "desmoines":
        # One live principal-office line was printed DESMOINES with no space.
        return "Polk", "city_spelling_desmoines"
    if not key:
        return "", "unknown"
    if key in SPLIT:
        return "", "split_city_unresolved"
    if key in POLK:
        return "Polk", "unique_city"
    if key in DALLAS:
        return "Dallas", "unique_city"
    if key in WARREN:
        return "Warren", "unique_city"
    return "", "outside_or_unlisted"
