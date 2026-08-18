"""Amazon-inspired, source-grounded product cards for the Streamlit UI."""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from contracts import ComparisonProduct, StepEvent, TopRecommendation


MAX_GRID_PRODUCTS = 6


SHOPPING_GRID_CSS = """
.shopping-grid-shell {
    container-name: shopping-results;
    container-type: inline-size;
    width: 100%;
}

.shopping-grid {
    display: grid;
    gap: 0.85rem;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin: 0.35rem 0 1rem;
}

.shopping-card {
    background: #ffffff;
    border: 1px solid #d5d9d9;
    border-radius: 12px;
    box-shadow: 0 1px 2px rgba(15, 17, 17, 0.06);
    color: #0f1111;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    transition: border-color 150ms ease, box-shadow 150ms ease,
        transform 150ms ease;
}

.shopping-card:hover {
    border-color: #aeb4b4;
    box-shadow: 0 5px 16px rgba(15, 17, 17, 0.12);
    transform: translateY(-2px);
}

.shopping-card__image-stage {
    align-items: center;
    background: #f7f7f7;
    display: flex;
    height: 215px;
    justify-content: center;
    padding: 0.75rem;
    position: relative;
}

.shopping-card__image {
    height: 100%;
    max-width: 100%;
    object-fit: contain;
    width: 100%;
}

.shopping-card__placeholder {
    align-items: center;
    color: #879092;
    display: flex;
    flex-direction: column;
    font-size: 2.4rem;
    gap: 0.35rem;
    justify-content: center;
    text-align: center;
}

.shopping-card__placeholder small {
    font-size: 0.75rem;
    font-weight: 650;
}

.shopping-card__body {
    display: flex;
    flex: 1;
    flex-direction: column;
    padding: 0.85rem 0.9rem 0.95rem;
}

.shopping-card__badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-bottom: 0.6rem;
    min-height: 1.45rem;
}

.shopping-source-badge,
.shopping-change-badge,
.shopping-top-badge {
    align-items: center;
    border-radius: 999px;
    display: inline-flex;
    font-size: 0.67rem;
    font-weight: 750;
    letter-spacing: 0.015em;
    line-height: 1;
    padding: 0.38rem 0.55rem;
    white-space: nowrap;
}

.shopping-source-badge--catalog {
    background: #e7f1fa;
    color: #174f7a;
}

.shopping-source-badge--web {
    background: #fff1d6;
    color: #7a4800;
}

.shopping-change-badge {
    background: #fff0f0;
    color: #a32727;
}

.shopping-top-badge {
    background: #067d62;
    color: #ffffff;
}

.shopping-card__title {
    color: #0f1111 !important;
    display: -webkit-box;
    font-size: 0.95rem;
    font-weight: 650;
    line-height: 1.35;
    min-height: 3.85rem;
    overflow: hidden;
    text-decoration: none !important;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
}

.shopping-card__title:hover {
    color: #c45500 !important;
    text-decoration: underline !important;
}

.shopping-card__rating {
    align-items: center;
    color: #565959;
    display: flex;
    font-size: 0.76rem;
    gap: 0.32rem;
    margin-top: 0.45rem;
    min-height: 1.1rem;
}

.shopping-card__stars {
    color: #de7921;
    font-size: 1rem;
}

.shopping-card__price-label {
    color: #565959;
    font-size: 0.68rem;
    margin-top: 0.7rem;
}

.shopping-card__price {
    align-items: flex-start;
    display: flex;
    line-height: 1;
    margin-top: 0.12rem;
    min-height: 2.25rem;
}

.shopping-card__currency {
    font-size: 0.78rem;
    margin-top: 0.23rem;
}

.shopping-card__whole {
    font-size: 1.75rem;
    font-weight: 500;
    letter-spacing: -0.035em;
}

.shopping-card__cents {
    font-size: 0.78rem;
    margin-top: 0.15rem;
}

.shopping-card__price-text {
    font-size: 1.22rem;
    font-weight: 650;
    line-height: 1.25;
}

.shopping-card__price-unavailable {
    color: #565959;
    font-size: 0.86rem;
    font-weight: 600;
    line-height: 1.3;
}

.shopping-card__history {
    color: #565959;
    font-size: 0.72rem;
    line-height: 1.35;
    margin-top: 0.32rem;
    min-height: 1rem;
}

.shopping-card__availability {
    color: #067d62;
    font-size: 0.77rem;
    font-weight: 650;
    line-height: 1.3;
    margin-top: 0.65rem;
}

.shopping-card__note,
.shopping-card__meta {
    color: #565959;
    font-size: 0.7rem;
    line-height: 1.4;
    margin-top: 0.45rem;
}

.shopping-card__note {
    display: -webkit-box;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
}

.shopping-card__match {
    background: #edf8f3;
    border-left: 3px solid #067d62;
    border-radius: 5px;
    color: #23443b;
    display: -webkit-box;
    font-size: 0.7rem;
    line-height: 1.4;
    margin-top: 0.55rem;
    overflow: hidden;
    padding: 0.42rem 0.5rem;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
}

.shopping-card__source-note {
    color: #6f7373;
    font-size: 0.68rem;
    line-height: 1.35;
    margin-top: 0.55rem;
}

.shopping-card__cta {
    background: #ffd814;
    border: 1px solid #fcd200;
    border-radius: 999px;
    box-shadow: 0 2px 5px rgba(213, 217, 217, 0.5);
    color: #0f1111 !important;
    display: block;
    font-size: 0.75rem;
    font-weight: 650;
    margin-top: auto;
    padding: 0.48rem 0.7rem;
    text-align: center;
    text-decoration: none !important;
}

.shopping-card__cta:hover {
    background: #f7ca00;
    border-color: #f2c200;
}

@container shopping-results (max-width: 720px) {
    .shopping-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@container shopping-results (max-width: 455px) {
    .shopping-grid {
        grid-template-columns: minmax(0, 1fr);
    }
}

@media (max-width: 700px) {
    .shopping-grid {
        grid-template-columns: minmax(0, 1fr);
    }
}
"""


def format_money(value: float | int | str | None) -> str:
    """Format a known price without trying to parse malformed source text."""
    if value is None:
        return "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"${value:,.2f}"
    return str(value)


def _safe_http_url(value: str | None) -> str | None:
    """Return an escaped HTTP(S) URL, rejecting unsafe link schemes."""
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return escape(value, quote=True)


def _price_html(value: float | int | str | None) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        whole, cents = f"{value:,.2f}".split(".")
        return (
            '<span class="shopping-card__currency">$</span>'
            f'<span class="shopping-card__whole">{whole}</span>'
            f'<sup class="shopping-card__cents">{cents}</sup>'
        )
    if value is None:
        return '<span class="shopping-card__price-unavailable">Price unavailable</span>'
    return f'<span class="shopping-card__price-text">{escape(str(value))}</span>'


def _shorten(value: str, limit: int = 145) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _web_status_note(product: ComparisonProduct, web_step: StepEvent | None) -> str:
    if product.private is None:
        return "No reliable catalog match; showing a web result."
    if product.live is not None:
        return ""
    if web_step is not None and web_step.status == "error":
        return "Web search was unavailable; showing the grounded catalog result."
    if web_step is not None and web_step.status == "completed":
        return "No confirmed web match was found for this catalog product."
    return "Catalog result; no confirmed web match is attached."


def product_card_html(
    product: ComparisonProduct,
    web_step: StepEvent | None = None,
    top_recommendation: TopRecommendation | None = None,
) -> str:
    """Render one unified shopping card with per-source provenance badges."""
    private = product.private
    live = product.live

    title = (
        live.title
        if live is not None
        else private.title
        if private is not None
        else "Product"
    )
    link = _safe_http_url(
        live.url if live is not None else private.product_url if private else None
    )
    image = _safe_http_url(
        live.image_url
        if live is not None and live.image_url
        else private.image_url if private is not None else None
    )

    badges: list[str] = []
    if top_recommendation is not None:
        badges.append(
            '<span class="shopping-top-badge">Top recommendation</span>'
        )
    if private is not None:
        badges.append(
            '<span class="shopping-source-badge shopping-source-badge--catalog">Catalog</span>'
        )
    if live is not None:
        badges.append(
            '<span class="shopping-source-badge shopping-source-badge--web">Web search</span>'
        )
    if any(conflict.field == "price" for conflict in product.conflicts):
        badges.append('<span class="shopping-change-badge">Price changed</span>')

    if image:
        image_html = (
            f'<img class="shopping-card__image" src="{image}" '
            f'alt="{escape(title, quote=True)}" loading="lazy" referrerpolicy="no-referrer">'
        )
    else:
        image_html = (
            '<div class="shopping-card__placeholder" aria-label="No product image">'
            '<span aria-hidden="true">▧</span><small>Image unavailable</small></div>'
        )

    title_html = escape(title)
    if link:
        title_html = (
            f'<a class="shopping-card__title" href="{link}" target="_blank" '
            f'rel="noopener noreferrer">{title_html}</a>'
        )
    else:
        title_html = f'<div class="shopping-card__title">{title_html}</div>'

    if live is not None and live.rating is not None:
        rating_html = (
            f'<span class="shopping-card__stars" role="img" '
            f'aria-label="{live.rating:.1f} out of 5 stars">★</span>'
            f'<span>{live.rating:.1f} / 5</span>'
        )
    else:
        rating_html = "<span>No rating reported</span>"

    private_price = None
    if private is not None:
        private_price = private.price_low if private.price_low is not None else private.price
    live_has_price = live is not None and live.price is not None
    primary_price = live.price if live_has_price else private_price
    price_label = (
        "Current web price"
        if live_has_price
        else "2020 catalog price"
        if private
        else "Price"
    )

    history_html = ""
    if private is not None and live_has_price:
        history_html = (
            '<div class="shopping-card__history">'
            f'2020 catalog: {escape(format_money(private_price))}</div>'
        )

    availability_html = ""
    if live is not None and live.availability:
        availability_html = (
            '<div class="shopping-card__availability">'
            f'{escape(live.availability)}</div>'
        )

    detail_parts: list[str] = []
    if private is not None and private.brand:
        detail_parts.append(private.brand)
    if private is not None and private.category:
        detail_parts.append(private.category)
    meta_html = ""
    if detail_parts:
        meta_html = (
            '<div class="shopping-card__meta">'
            f'{escape(" · ".join(detail_parts))}</div>'
        )

    note_html = ""
    if live is not None and live.snippet:
        note_html = (
            '<div class="shopping-card__note">'
            f'{escape(_shorten(live.snippet))}</div>'
        )

    match_html = ""
    if private is not None and private.feature_evidence:
        match_html = (
            '<div class="shopping-card__match"><strong>Matched detail:</strong> '
            f'{escape(_shorten(private.feature_evidence[0], 155))}</div>'
        )

    source_note = _web_status_note(product, web_step)
    source_note_html = (
        f'<div class="shopping-card__source-note">{escape(source_note)}</div>'
        if source_note
        else ""
    )

    if link:
        cta_label = "View web result" if live is not None else "View catalog listing"
        cta_html = (
            f'<a class="shopping-card__cta" href="{link}" target="_blank" '
            f'rel="noopener noreferrer">{cta_label}</a>'
        )
    else:
        cta_html = ""

    return "".join(
        [
            '<article class="shopping-card">',
            '<div class="shopping-card__image-stage">',
            image_html,
            "</div>",
            '<div class="shopping-card__body">',
            '<div class="shopping-card__badges">',
            "".join(badges),
            "</div>",
            title_html,
            '<div class="shopping-card__rating">',
            rating_html,
            "</div>",
            f'<div class="shopping-card__price-label">{price_label}</div>',
            '<div class="shopping-card__price">',
            _price_html(primary_price),
            "</div>",
            history_html,
            availability_html,
            meta_html,
            match_html,
            note_html,
            source_note_html,
            cta_html,
            "</div></article>",
        ]
    )


def shopping_grid_html(
    products: list[ComparisonProduct],
    web_steps: list[StepEvent] | None = None,
    top_recommendation: TopRecommendation | None = None,
) -> str:
    """Render up to six product cards in one responsive shopping grid."""
    steps = web_steps or []
    first_identity = ""
    if products:
        first = products[0]
        first_identity = (
            f"catalog:{first.private.doc_id}"
            if first.private is not None
            else f"live:{first.live.url}"
            if first.live is not None
            else ""
        )
    canonical_top = (
        top_recommendation
        if top_recommendation is not None
        and top_recommendation.product_key == first_identity
        else None
    )
    cards = [
        product_card_html(
            product,
            steps[index] if index < len(steps) else None,
            canonical_top if index == 0 else None,
        )
        for index, product in enumerate(products[:MAX_GRID_PRODUCTS])
    ]
    return (
        '<div class="shopping-grid-shell">'
        '<div class="shopping-grid">'
        + "".join(cards)
        + "</div></div>"
    )


def comparison_rows(products: list[ComparisonProduct]) -> list[dict[str, str]]:
    """Build the assignment-required compact comparison table under the cards."""
    rows = []
    for product in products[:MAX_GRID_PRODUCTS]:
        private = product.private
        live = product.live
        title = (
            live.title
            if live is not None
            else private.title
            if private
            else "Product"
        )
        sources = []
        if private is not None:
            sources.append("Catalog")
        if live is not None:
            sources.append("Web search")
        shown_price = (
            live.price
            if live is not None and live.price is not None
            else private.price_low
            if private is not None and private.price_low is not None
            else private.price
            if private is not None
            else None
        )
        catalog_price = (
            private.price_low
            if private is not None and private.price_low is not None
            else private.price
            if private is not None
            else None
        )
        rows.append(
            {
                "Product": title,
                "Sources": " + ".join(sources),
                "Price shown": format_money(shown_price),
                "Catalog (2020)": format_money(catalog_price),
                "Web rating": (
                    f"{live.rating:.1f}"
                    if live and live.rating is not None
                    else "—"
                ),
                "Availability": live.availability if live and live.availability else "—",
                "Matched details": (
                    " · ".join(
                        _shorten(item, 100)
                        for item in private.feature_evidence[:2]
                    )
                    if private is not None and private.feature_evidence
                    else "—"
                ),
                "Ingredients": "— (not in catalog)",
            }
        )
    return rows
