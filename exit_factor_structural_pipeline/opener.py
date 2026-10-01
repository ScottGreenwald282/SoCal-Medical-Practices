"""Deterministic evidence-only opener. Claude is not called."""

from __future__ import annotations


CLAUDE_STATUS = "unavailable"


def factual_opener(
    *,
    owner_name: str,
    owner_title: str,
    company: str,
    filing_sentence: str,
    job_sentence: str,
) -> str:
    if not owner_name or not owner_title or not company:
        return ""
    return (
        f"{owner_name} is named as {owner_title} of {company} on the ownership source. "
        f"{filing_sentence} {job_sentence} "
        "This note records those public facts only."
    )
