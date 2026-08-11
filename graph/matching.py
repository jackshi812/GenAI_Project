"""Pure deterministic helpers: title matching, variant guards, price-conflict
math, currency-keyword escalation, fixture keys, filter cleaning.

Standard library only — no contracts.py, no LangGraph, no LangChain — so
`python -m graph.test_deterministic` runs with nothing installed. Other graph
modules import from here.

Stages:
  A. normalized-title similarity shortlist (difflib.SequenceMatcher)
  B. deterministic variant guards (pack / count / size-unit / model / color)
  C. selective LLM confirmation, only for the ambiguous band (handled by the
     Retriever; this module just says which band a pair falls in)
"""

import re
from difflib import SequenceMatcher

# --- deterministic source escalation (GRAPH-03, spec §234) -----------------
# Word-boundary regexes: "now" must not fire on "know", "snow", "nowhere".
# The LLM planner may escalate additionally but can never veto a keyword hit.
_CURRENCY_PATTERNS = [
    re.compile(p)
    for p in (
        r"\bcurrent\s+price\b",
        r"\bcurrent\b",
        r"\bright\s+now\b",
        r"\bnow\b",
        r"\blatest\b",
        r"\btoday\b",
        r"\bavailability\b",
        r"\bin\s+stock\b",
        r"\bstill\s+available\b",
    )
]


def currency_keyword_hit(transcript: str) -> bool:
    t = transcript.lower()
    return any(p.search(t) for p in _CURRENCY_PATTERNS)


# --- tool-seam text rules (D-08, Ginger/README filter seam) ----------------
# The only rag.search filter keys ever forwarded.
ALLOWED_RAG_FILTERS = ("price_max", "price_min", "category", "brand", "k")


def clean_filters(filters: dict) -> dict:
    """Keep only allowed rag.search filter keys and drop null values."""
    return {
        k: v for k, v in (filters or {}).items() if k in ALLOWED_RAG_FILTERS and v is not None
    }


def eight_word_key(text: str) -> str:
    """Shared fixture key rule (D-08): first eight whitespace-delimited words,
    lowercased, whitespace collapsed. Used both to build live queries from
    catalog titles and to look up recorded fixture responses. Exact match
    only — a miss returns nothing rather than a fuzzy neighbour."""
    words = [w for w in re.split(r"\s+", text.strip().lower()) if w]
    return " ".join(words[:8])


# Thresholds from D-01.
ACCEPT_THRESHOLD = 0.60
REJECT_THRESHOLD = 0.35

# Only this fixed filler set is dropped — never numbers, units, model strings,
# or colors.
_FILLER = {"the", "a", "an", "for", "with", "and", "of", "by"}

_COLORS = {
    "black", "white", "red", "blue", "green", "pink", "purple", "yellow",
    "grey", "gray", "brown", "orange", "teal", "silver", "gold", "amethyst",
}

_UNITS = (
    "oz", "ounce", "ounces", "inch", "inches", "in", "ft", "feet", "lb",
    "lbs", "pound", "pounds", "ml", "l", "cm", "mm", "gallon", "quart",
)

_PACK_RE = re.compile(r"\b(\d+)\s*[- ]?pack\b|\bpack\s+of\s+(\d+)\b")
_COUNT_RE = re.compile(r"\b(\d+)\s*[- ]?(?:pieces?|pcs?|count|ct|darts?|cards?|balls?)\b")
_SIZE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(%s)\b" % "|".join(_UNITS))
# Model-ish token: letters+digits mixed (10713 handled below), e.g. "mxvii-10k".
_ALNUM_MODEL_RE = re.compile(r"\b(?=\w*\d)(?=\w*[a-z])[a-z0-9]+(?:-[a-z0-9]+)*\b")
# Pure digit runs of 4-6 digits (set numbers like 10713, 14796).
_DIGIT_MODEL_RE = re.compile(r"\b\d{4,6}\b")


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, drop only the fixed filler set."""
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    words = [w for w in t.split() if w not in _FILLER]
    return " ".join(words)


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def extract_variant_tokens(title: str) -> dict:
    """Extract explicit variant evidence from a title.

    Returns {"pack": set, "count": set, "size": set, "model": set,
    "color": set}; empty set means the title states nothing on that dimension.
    """
    t = title.lower()
    t_clean = re.sub(r"[^\w\s.-]", " ", t)

    pack = set()
    for m in _PACK_RE.finditer(t_clean):
        pack.add(int(m.group(1) or m.group(2)))

    count = {int(m.group(1)) for m in _COUNT_RE.finditer(t_clean)}

    size = {(float(m.group(1)), _canon_unit(m.group(2))) for m in _SIZE_RE.finditer(t_clean)}

    # Model tokens: digit runs not already claimed as pack/count/size numbers.
    claimed = {str(n) for n in pack | count} | {
        ("%g" % v) for v, _ in size
    }
    model = set()
    for m in _DIGIT_MODEL_RE.finditer(t_clean):
        if m.group(0) not in claimed:
            model.add(m.group(0))
    for m in _ALNUM_MODEL_RE.finditer(t_clean):
        tok = m.group(0)
        if not _SIZE_RE.fullmatch(tok) and len(tok) >= 3:
            model.add(tok)

    color = {w for w in re.findall(r"[a-z]+", t_clean) if w in _COLORS}

    return {"pack": pack, "count": count, "size": size, "model": model, "color": color}


def _canon_unit(u: str) -> str:
    aliases = {
        "ounce": "oz", "ounces": "oz", "inches": "inch", "in": "inch",
        "feet": "ft", "lbs": "lb", "pound": "lb", "pounds": "lb",
    }
    return aliases.get(u, u)


def variant_guard(title_a: str, title_b: str) -> str:
    """Compare variant evidence between two titles.

    Returns:
      "conflict"   — both titles state a value on some dimension and disagree
                     (different pack size / count / model / size / color):
                     reject the match outright.
      "one_sided"  — at least one dimension has evidence on exactly one side:
                     missing evidence is not proof of equality, force LLM
                     confirmation even above the accept threshold.
      "compatible" — every stated dimension agrees on both sides.
    """
    a = extract_variant_tokens(title_a)
    b = extract_variant_tokens(title_b)
    one_sided = False
    for dim in ("pack", "count", "size", "model", "color"):
        va, vb = a[dim], b[dim]
        if va and vb:
            if not (va & vb):
                return "conflict"
        elif va or vb:
            one_sided = True
    return "one_sided" if one_sided else "compatible"


def match_band(score: float, guard: str) -> str:
    """Which path a candidate pair takes (D-01).

    "accept"  — score > 0.60 AND variant guards compatible: auto-accept.
    "reject"  — score < 0.35, or guards found a hard conflict: auto-reject.
    "confirm" — everything else (ambiguous band, or one-sided variant
                evidence): one LLM confirmation call.
    """
    if guard == "conflict":
        return "reject"
    if score < REJECT_THRESHOLD:
        return "reject"
    if score > ACCEPT_THRESHOLD and guard == "compatible":
        return "accept"
    return "confirm"


def price_conflict(private_price: float, live_price: float) -> dict | None:
    """Genuine price disagreement (D-02): differ by more than 10% of the
    private value or $2, whichever is larger. Returns a plain dict; the
    Retriever wraps it in contracts.Conflict."""
    threshold = max(0.10 * abs(private_price), 2.0)
    diff = live_price - private_price
    if abs(diff) <= threshold:
        return None
    return {
        "field": "price",
        "private_value": private_price,
        "live_value": live_price,
        "direction": "up" if diff > 0 else "down",
    }
