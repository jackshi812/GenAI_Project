"""Warm response helpers that never add facts beyond grounded evidence."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from contracts import ComparisonProduct, RagResult, ShoppingContext, WebResult
from graph.preferences import matched_preferences, preference_requirements


CLARIFICATION_PLAN = (
    "Clarifying question; product tools paused until the shopper names a "
    "category or use case."
)
REFINEMENT_PLAN = (
    "Preference refinement; previous results retained and product tools paused "
    "until the shopper says what should change."
)


_REJECTION_PATTERNS = (
    re.compile(
        r"\b(?:i\s+)?(?:do\s+not|don['’]?t)\s+like\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:i\s+)?(?:dislike|hate)\b", re.IGNORECASE),
    re.compile(r"\bnone\s+of\s+(?:them|these|those)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:not|isn['’]?t|aren['’]?t)\s+(?:what|quite)\s+"
        r"(?:i\s+)?(?:want|wanted|need|needed|like)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:(?:show|give|find)\s+me\s+)?(?:something|anything)\s+"
        r"(?:else|different)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:other|different)\s+options?\b", re.IGNORECASE),
    re.compile(r"\b(?:these|those|they)\s+(?:do\s+not|don['’]?t)\s+work\b", re.I),
    re.compile(r"\b(?:not\s+for\s+me|try\s+again)\b", re.IGNORECASE),
)

_DELEGATED_CHOICE_PATTERNS = (
    re.compile(r"\bi\s+(?:do\s+not|don['’]?t)\s+know\b", re.IGNORECASE),
    re.compile(r"\bhelp\s+me\s+(?:choose|decide|pick)\b", re.IGNORECASE),
    re.compile(r"\b(?:you|please)\s+(?:choose|decide|pick)\b", re.IGNORECASE),
    re.compile(r"\b(?:choose|decide|pick)\s+for\s+me\b", re.IGNORECASE),
    re.compile(r"\bsurprise\s+me\b", re.IGNORECASE),
    re.compile(
        r"\b(?:anything|whatever)\s+(?:is\s+fine|works|you\s+think)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:just\s+)?(?:give|show|find)\s+me"
        r"(?:\s+(?:give|show|find)\s+me)?\s+(?:anything|something)\b",
        re.IGNORECASE,
    ),
)


_VAGUE_TERMS = {
    "affordable",
    "anything",
    "best",
    "cheap",
    "cool",
    "find",
    "fun",
    "gift",
    "gifts",
    "good",
    "home",
    "house",
    "item",
    "items",
    "look",
    "looking",
    "need",
    "nice",
    "option",
    "options",
    "product",
    "products",
    "random",
    "recommend",
    "recommendation",
    "recommendations",
    "show",
    "should",
    "something",
    "stuff",
    "surprise",
    "thing",
    "things",
    "want",
}
_NEED_STOPWORDS = _VAGUE_TERMS | {
    "a",
    "an",
    "and",
    "buy",
    "don",
    "dont",
    "find",
    "for",
    "i",
    "me",
    "of",
    "please",
    "show",
    "the",
    "them",
    "these",
    "those",
    "want",
}


def _ascii_words(value: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", str(value))
    ascii_value = folded.encode("ascii", "ignore").decode("ascii").casefold()
    return re.findall(r"[a-z0-9]+", ascii_value)


def _normalized_word(value: str) -> str:
    if value.endswith("ies") and len(value) > 4:
        return f"{value[:-3]}y"
    if value.endswith("s") and len(value) > 3:
        return value[:-1]
    return value


def is_vague_shopping_query(query: str) -> bool:
    """Return true when a query has no product, category, or use-case cue."""
    terms = set(_ascii_words(query))
    return not terms or terms.issubset(_VAGUE_TERMS)


def is_rejection_followup(transcript: str) -> bool:
    """Recognize dissatisfaction as dialogue feedback, not a product name."""
    text = str(transcript or "").strip()
    return bool(text) and any(pattern.search(text) for pattern in _REJECTION_PATTERNS)


def is_delegated_choice(transcript: str) -> bool:
    """Recognize when the shopper explicitly asks the agent to decide."""
    text = str(transcript or "").strip()
    return bool(text) and any(
        pattern.search(text) for pattern in _DELEGATED_CHOICE_PATTERNS
    )


def clarification_reply(
    budget_max: float | None,
    *,
    transcript: str = "",
) -> str:
    """Ask one warm, bounded question before searching an underspecified query."""
    text = str(transcript or "").casefold()
    budget_note = (
        f" I’ll keep the ${budget_max:,.0f} budget."
        if budget_max is not None
        else ""
    )
    if re.search(r"\b(?:home|house)\b", text):
        return (
            "For your home, what problem would you most like this purchase "
            f"to solve?{budget_note}"
        )
    if re.search(r"\bgifts?\b", text):
        return f"Who is the gift for, and what are they interested in?{budget_note}"
    if budget_max is not None:
        return (
            f"With ${budget_max:,.0f} to work with, what would you like the item "
            "to help with, or who is it for?"
        )
    return (
        "What would you like the item to help with, or who is it for?"
    )


def refinement_reply(budget_max: float | None) -> str:
    """Acknowledge rejected results and ask for one actionable preference."""
    if budget_max is not None:
        return (
            "Got it—let’s change direction. What should I adjust: the product "
            f"type, brand, or a specific feature? I’ll keep your ${budget_max:,.0f} limit."
        )
    return (
        "Got it—let’s change direction. What should I adjust: the product "
        "type, price, brand, or a specific feature?"
    )


def preference_clarification_reply(
    transcript: str,
    budget_max: float | None,
) -> str:
    """Ask for the missing value when a requested preference change is incomplete."""
    text = str(transcript or "").casefold()
    facet = (
        "color"
        if "color" in text or "colour" in text
        else "size"
        if "size" in text or "larger" in text or "smaller" in text
        else "material"
        if "material" in text or "made of" in text
        else "texture"
        if "texture" in text or "feel" in text
        else "comfort feature"
        if "comfort" in text
        else "feature"
    )
    budget_note = (
        f" I’ll keep the ${budget_max:,.0f} limit."
        if budget_max is not None
        else ""
    )
    return f"Sure—what {facet} would you prefer instead?{budget_note}"


def _pick_variant(key: str, options: tuple[str, ...]) -> str:
    """Choose stable wording without making test or demo output random."""
    digest = hashlib.blake2s(key.encode("utf-8"), digest_size=2).digest()
    return options[int.from_bytes(digest, "big") % len(options)]


def _product_opening(title: str, feature: str | None, *, key: str) -> str:
    if feature:
        template = _pick_variant(
            key,
            (
                "{title} looks promising. It includes {feature}.",
                "A strong option is {title}, with {feature}.",
                "Here’s a useful match: {title}. It has {feature}.",
                "I found a good possibility in {title}. It comes with {feature}.",
            ),
        )
        return template.format(title=title, feature=feature)
    template = _pick_variant(
        key,
        (
            "{title} looks like a solid option.",
            "One possibility worth considering is {title}.",
            "Here’s a potential match: {title}.",
            "I found {title} as a possible fit.",
        ),
    )
    return template.format(title=title)


def _web_opening(
    title: str,
    feature: str | None,
    *,
    key: str,
    origin: str,
) -> str:
    source = "current web results" if origin == "live_serper" else "web results"
    if feature:
        template = _pick_variant(
            key,
            (
                "From the {source}, {title} stands out. It includes {feature}.",
                "A web option to consider is {title}, with {feature}.",
                "Here’s a promising web match: {title}. It has {feature}.",
            ),
        )
        return template.format(
            source=source,
            title=title,
            feature=feature,
        )
    template = _pick_variant(
        key,
        (
            "From the {source}, {title} looks promising.",
            "A web option worth considering is {title}.",
            "Here’s a potential web match: {title}.",
        ),
    )
    return template.format(source=source, title=title)


def _short_title(title: str, limit: int = 7) -> str:
    segments = [part.strip(" -") for part in re.split(r"\s+-\s+", title)]
    segments = [part for part in segments if part]
    if len(segments) >= 2:
        candidate = " ".join(segments[:2])
    else:
        candidate = re.split(
            r"\b(?:with|includes|including)\b",
            title,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
    candidate = re.sub(r"\s*\([^)]*\)\s*", " ", candidate)
    words = candidate.split()[:limit]
    return " ".join(words).rstrip(",.;:-")


def _feature_phrase(title: str) -> str | None:
    piece_match = re.search(
        r"\b(\d[\d,]*)\s*[- ]?\s*piece\s+"
        r"(jigsaw\s+puzzle|puzzle|set|kit)\b",
        title,
        re.IGNORECASE,
    )
    if piece_match:
        count, item = piece_match.groups()
        return f"a {count}-piece {item.casefold()}"

    with_match = re.search(
        r"\bwith\s+(.+?)(?:\s+for\b|\s*\(|$)",
        title,
        re.IGNORECASE,
    )
    if with_match:
        parts = [
            part.strip(" ,.;:-")
            for part in re.split(r",|\band\b|&", with_match.group(1), flags=re.I)
            if part.strip(" ,.;:-")
        ][:2]
        if parts:
            phrase = " and ".join(part.casefold() for part in parts)
            if not re.match(r"^(?:a|an|the|\d)\b", phrase):
                phrase = f"a {phrase}"
            return phrase

    pieces_match = re.search(r"\b(\d[\d,]*)\s+pieces\b", title, re.IGNORECASE)
    if pieces_match:
        return f"{pieces_match.group(1)} pieces"
    return None


def _need_phrase(query: str, title: str) -> str | None:
    title_terms = {_normalized_word(term) for term in _ascii_words(title)}
    matching = [
        term
        for term in _ascii_words(query)
        if term not in _NEED_STOPWORDS
        and _normalized_word(term) in title_terms
    ]
    if not matching:
        return None
    return " ".join(dict.fromkeys(matching))[:40]


def _money(value: float | str | None) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"${float(value):,.2f}"
    raw = str(value or "").strip()
    return raw or None


def catalog_recommendation(
    product: RagResult,
    *,
    query: str,
    budget_max: float | None,
    checking_live: bool,
    current_price: float | None = None,
    decisive: bool = False,
) -> str:
    """Compose a warm recommendation using only catalog title and price facts."""
    title = _short_title(product.title)
    feature = _feature_phrase(product.title)
    need = _need_phrase(query, product.title)
    price = _money(
        product.price_low if product.price_low is not None else product.price
    )
    variant_key = f"catalog|{product.doc_id}|{query}"
    if decisive:
        opening = f"I’d go with {title}."
        if feature:
            opening += f" It includes {feature}."
    else:
        opening = _product_opening(title, feature, key=variant_key)

    reasons: list[str] = []
    fits_budget = (
        budget_max is not None
        and product.budget_fit == "within"
        and product.price_low is not None
        and product.price_low <= budget_max
    )
    current = _money(current_price)
    if current is not None and price:
        if budget_max is not None and current_price is not None:
            if current_price <= budget_max:
                reasons.append(
                    f"Its current web price is {current}, within your "
                    f"${budget_max:,.0f} budget; the 2020 catalog price was {price}."
                )
            else:
                reasons.append(
                    f"The 2020 catalog price was {price}, but its current web "
                    f"price is {current}, above your ${budget_max:,.0f} budget."
                )
        else:
            reasons.append(
                f"The 2020 catalog price was {price}; its current web price is {current}."
            )
    elif fits_budget and price:
        if need and not feature:
            reasons.append(
                f"It matches your {need} request. At {price} in the 2020 "
                f"catalog, it fits your ${budget_max:,.0f} budget."
            )
        else:
            reasons.append(
                f"At {price} in the 2020 catalog, it fits your "
                f"${budget_max:,.0f} budget."
            )
    elif need and price:
        subject = "That" if feature else "It"
        reasons.append(
            f"{subject} matches your {need} request at a {price} 2020 catalog price."
        )
    elif price:
        reasons.append(f"Its 2020 catalog price is {price}.")
    elif need:
        subject = "That" if feature else "It"
        reasons.append(f"{subject} matches your {need} request.")

    live_sentence = "I’m checking current listings too." if checking_live else ""
    text = " ".join(part for part in [opening, *reasons, live_sentence] if part)
    if len(text.split()) <= 30:
        return text

    # Long marketplace titles can consume the speech budget. This fallback
    # keeps the evidence and fit rationale while dropping only extra detail.
    compact = (
        f"I’d go with {title}."
        if decisive
        else _product_opening(title, None, key=variant_key)
    )
    if current is not None and price:
        compact += f" Catalog {price} in 2020; current web price {current}."
    elif fits_budget and price:
        compact += (
            f" Its {price} catalog price fits your ${budget_max:,.0f} budget."
        )
    elif need:
        compact += f" It matches your {need} request."
    elif price:
        compact += f" Its 2020 catalog price is {price}."
    if checking_live:
        compact += " I’m checking current listings too."
    return compact


def web_recommendation(
    product: WebResult,
    *,
    query: str,
    budget_max: float | None,
    numeric_price: float | None,
    decisive: bool = False,
) -> str:
    """Compose a warm web-only recommendation with explicit provenance."""
    title = _short_title(product.title)
    feature = _feature_phrase(product.title)
    need = _need_phrase(query, product.title)
    price = _money(numeric_price)
    if product.origin == "live_serper":
        price_source = "current web price"
    elif product.origin == "recorded_fixture":
        price_source = "recorded web price"
    else:
        price_source = "web price"
    variant_key = f"web|{product.url}|{query}"
    if decisive:
        opening = f"I’d choose {title}."
        if feature:
            opening += f" It includes {feature}."
    else:
        opening = _web_opening(
            title,
            feature,
            key=variant_key,
            origin=product.origin,
        )

    reasons: list[str] = []
    if price and budget_max is not None and numeric_price is not None:
        if numeric_price <= budget_max:
            reasons.append(
                f"Its {price_source} is {price}, which fits your "
                f"${budget_max:,.0f} budget."
            )
        else:
            reasons.append(
                f"Its {price_source} is {price}, above your ${budget_max:,.0f} budget."
            )
    elif need and price:
        reasons.append(
            f"It matches your {need} request at a {price} {price_source}."
        )
    elif price:
        reasons.append(f"Its {price_source} is {price}.")
    elif need:
        reasons.append(f"It matches your {need} request.")

    text = " ".join([opening, *reasons])
    if len(text.split()) <= 30:
        return text
    compact = (
        f"I’d choose {title}."
        if decisive
        else _web_opening(
            title,
            None,
            key=variant_key,
            origin=product.origin,
        )
    )
    if price:
        compact += f" Its {price_source} is {price}."
    elif need:
        compact += f" It matches your {need} request."
    return compact


def grounded_comparison(
    products: list[ComparisonProduct],
    context: ShoppingContext | dict | None,
    *,
    budget_max: float | None = None,
) -> str:
    """Compare two leading options using only explicitly supported attributes."""
    candidates = [product for product in products if product.private or product.live]
    if not candidates:
        return "I couldn’t confirm a grounded product for that request."
    if len(candidates) == 1:
        product = candidates[0]
        if product.private is not None:
            return catalog_recommendation(
                product.private,
                query=(context.resolved_query if isinstance(context, ShoppingContext) else ""),
                budget_max=budget_max,
                checking_live=False,
            )
        return web_recommendation(
            product.live,
            query=(context.resolved_query if isinstance(context, ShoppingContext) else ""),
            budget_max=budget_max,
            numeric_price=None,
        )

    first, second = candidates[:2]

    def title(product: ComparisonProduct) -> str:
        raw = product.live.title if product.live is not None else product.private.title
        return _short_title(raw, limit=5)

    first_matches = matched_preferences(first, context)
    second_matches = matched_preferences(second, context)
    requirements = preference_requirements(context)
    first_fit = ", ".join(first_matches[:2])
    second_fit = ", ".join(second_matches[:2])
    key = "|".join((title(first), title(second), *requirements))

    if first_fit and second_fit:
        if len(first_matches) > len(second_matches):
            templates = (
                "{first} leads for {first_fit}; {second} also confirms {second_fit}. "
                "The first supports more of your stated preferences.",
                "I’d compare {first}, which confirms {first_fit}, with {second}, "
                "which confirms {second_fit}; the first supports more of your request.",
                "{first} is the closer fit for {first_fit}. {second} is the best "
                "alternative and confirms {second_fit}.",
            )
        elif set(first_matches) == set(second_matches):
            templates = (
                "Both {first} and {second} confirm {first_fit}; these are the "
                "strongest evidenced options.",
                "{first} and {second} each confirm {first_fit}. Their grounded "
                "details make them close alternatives.",
                "On confirmed details, {first} and {second} tie at {first_fit}.",
            )
        else:
            templates = (
                "The tradeoff is clear: {first} confirms {first_fit}, while "
                "{second} confirms {second_fit}.",
                "I’d compare {first} for {first_fit} with {second} for {second_fit}; "
                "each confirms a different part of your request.",
                "{first} confirms {first_fit}; {second} confirms {second_fit}. "
                "Those are the strongest evidenced tradeoffs among the results.",
            )
        text = _pick_variant(key, templates).format(
            first=title(first),
            second=title(second),
            first_fit=first_fit,
            second_fit=second_fit,
        )
    elif first_fit:
        text = (
            f"{title(first)} is the strongest evidenced match for {first_fit}. "
            f"{title(second)} is another grounded candidate."
        )
    else:
        text = (
            f"{title(first)} and {title(second)} are the closest grounded candidates."
        )

    words = text.split()
    if len(words) <= 30:
        return text
    compact = " ".join(words[:30]).rstrip(" ,;:-")
    if not re.search(r"[.!?]$", compact):
        compact += "."
    return compact
