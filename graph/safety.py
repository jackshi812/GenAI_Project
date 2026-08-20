"""Deterministic safety policy shared by every response path."""

from __future__ import annotations

import re


SAFETY_FLAG = "hazardous_chemical_mixing"
SAFETY_RATIONALE = (
    "Safety warning: I can’t help with hazardous chemical mixing. Don’t mix "
    "household cleaners; use each only as labeled, ventilate, and contact a "
    "poison center after exposure."
)

_MIXING_CUE = re.compile(
    r"\b(?:mix(?:es|ed|ing)?|combin(?:e|es|ed|ing)|blend(?:s|ed|ing)?|"
    r"add(?:s|ed|ing)?|together)\b",
    re.IGNORECASE,
)
_BLEACH = re.compile(r"\b(?:bleach|chlorine)(?:[- ]based)?\b", re.IGNORECASE)
_AMMONIA = re.compile(r"\bammonia(?:[- ]based)?\b", re.IGNORECASE)
_ACID_OR_VINEGAR = re.compile(
    r"\b(?:acid|acidic|acetic\s+acid|vinegar|vinager|vineager|vingar)\b",
    re.IGNORECASE,
)
_VINEGAR = re.compile(
    r"\b(?:vinegar|vinager|vineager|vingar|acetic\s+acid)\b",
    re.IGNORECASE,
)


def is_hazardous_chemical_mixing(transcript: str) -> bool:
    """Recognize supported dangerous cleaner pairs, including common ASR typos."""
    text = str(transcript or "")
    if not _MIXING_CUE.search(text):
        return False
    has_bleach = bool(_BLEACH.search(text))
    has_ammonia = bool(_AMMONIA.search(text))
    has_acid_or_vinegar = bool(_ACID_OR_VINEGAR.search(text))
    has_vinegar = bool(_VINEGAR.search(text))
    return bool(
        (has_bleach and (has_ammonia or has_acid_or_vinegar))
        or (has_ammonia and has_vinegar)
    )
