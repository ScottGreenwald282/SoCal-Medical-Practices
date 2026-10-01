"""Exact legal-name matching. Substring overlap is not a match."""

from __future__ import annotations

import re

_SUFFIX_TOKENS = {
    "LLC",
    "INC",
    "INCORPORATED",
    "CO",
    "COMPANY",
    "CORP",
    "CORPORATION",
    "LLP",
    "PLLC",
    "PC",
    "THE",
    "AND",
}


def normalize_name(value: str) -> str:
    text = value.upper().replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\bL L C\b", " ", text)
    text = re.sub(r"\bL L P\b", " ", text)
    tokens = [tok for tok in text.split() if tok not in _SUFFIX_TOKENS]
    return " ".join(tokens)


def names_match(left: str, right: str) -> bool:
    a = normalize_name(left)
    b = normalize_name(right)
    if not a or not b:
        return False
    return a == b


def in_name_set(name: str, blocked: set[str]) -> bool:
    key = normalize_name(name)
    if not key:
        return False
    return key in blocked


_FIRST_ROLE = re.compile(r"\b(newly created|first-ever|first ever)\b", re.I)
_MGMT_TITLE = re.compile(
    r"\b(general manager|operations manager|chief operating officer|\bcoo\b)\b",
    re.I,
)


def is_explicit_first_role(text: str) -> bool:
    """True only when the posting itself says the role is new or first."""
    return bool(_FIRST_ROLE.search(text or "") and _MGMT_TITLE.search(text or ""))


def is_management_title(title: str) -> bool:
    return bool(_MGMT_TITLE.search(title or ""))
