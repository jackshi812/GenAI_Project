"""Amazon-inspired, source-grounded product cards for the Streamlit UI."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import fsum, isfinite
from urllib.parse import urlsplit

from app.cart import canonical_product_key
from contracts import ComparisonProduct, StepEvent, TopRecommendation


MAX_GRID_PRODUCTS = 6

_WEB_PRICE_LABELS = {
    "live_serper": "Current web price",
    "recorded_fixture": "Recorded web price",
    "unknown": "Web price",
}


@dataclass(frozen=True, slots=True)
class ProductDisplay:
    """Grounded fields shared by result cards, comparison rows, and the cart."""

    title: str
    image_url: str | None
    primary_price: float | int | str | None
    formatted_price: str
    price_label: str
    source_labels: tuple[str, ...]
    link: str | None


@dataclass(frozen=True, slots=True)
class PreparedProductCard:
    """One visible product paired with its positional presentation metadata."""

    index: int
    product: ComparisonProduct
    display: ProductDisplay
    web_step: StepEvent | None
    top_recommendation: TopRecommendation | None


@dataclass(frozen=True, slots=True)
class CartPriceSummary:
    """A truthful sum of only the cart prices safe to treat as numbers."""

    total: float
    included_count: int
    excluded_count: int
    price_sources: tuple[str, ...]


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


def safe_http_url(value: str | None) -> str | None:
    """Return an HTTP(S) URL unchanged, rejecting unsafe or relative links."""
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def _safe_http_url(value: str | None) -> str | None:
    """Return a safe URL escaped for interpolation into card HTML."""
    safe = safe_http_url(value)
    return escape(safe, quote=True) if safe is not None else None


def product_display(product: ComparisonProduct) -> ProductDisplay:
    """Select the exact grounded title, price provenance, sources, and link."""
    private = product.private
    live = product.live
    title = (
        live.title
        if live is not None
        else private.title
        if private is not None
        else "Product"
    )
    private_price = None
    if private is not None:
        private_price = (
            private.price_low
            if private.price_low is not None
            else private.price
        )
    live_has_price = live is not None and live.price is not None
    primary_price = live.price if live_has_price else private_price
    price_label = (
        _WEB_PRICE_LABELS[live.origin]
        if live_has_price and live is not None
        else "2020 catalog price"
        if private is not None
        else "Price"
    )
    source_labels: list[str] = []
    if private is not None:
        source_labels.append("Catalog")
    if live is not None:
        source_labels.append("Web search")
    link_candidate = (
        live.url
        if live is not None
        else private.product_url
        if private is not None
        else None
    )
    image_candidate = (
        live.image_url
        if live is not None and live.image_url
        else private.image_url
        if private is not None
        else None
    )
    return ProductDisplay(
        title=title,
        image_url=safe_http_url(image_candidate),
        primary_price=primary_price,
        formatted_price=format_money(primary_price),
        price_label=price_label,
        source_labels=tuple(source_labels),
        link=safe_http_url(link_candidate),
    )


def summarize_cart_prices(
    products: list[ComparisonProduct],
) -> CartPriceSummary:
    """Sum displayed numeric prices without parsing malformed source text."""
    numeric_prices: list[float] = []
    price_sources: list[str] = []
    excluded_count = 0
    for product in products:
        display = product_display(product)
        value = display.primary_price
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(float(value))
            and float(value) >= 0
        ):
            numeric_prices.append(float(value))
            if display.price_label not in price_sources:
                price_sources.append(display.price_label)
        else:
            excluded_count += 1
    return CartPriceSummary(
        total=fsum(numeric_prices),
        included_count=len(numeric_prices),
        excluded_count=excluded_count,
        price_sources=tuple(price_sources),
    )


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
    display = product_display(product)
    title = display.title
    link = _safe_http_url(display.link)
    image = _safe_http_url(display.image_url)

    badges: list[str] = []
    if top_recommendation is not None:
        badges.append(
            '<span class="shopping-top-badge">Top recommendation</span>'
        )
    if "Catalog" in display.source_labels:
        badges.append(
            '<span class="shopping-source-badge shopping-source-badge--catalog">Catalog</span>'
        )
    if "Web search" in display.source_labels:
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

    private_price = (
        private.price_low
        if private is not None and private.price_low is not None
        else private.price
        if private is not None
        else None
    )
    live_has_price = live is not None and live.price is not None
    primary_price = display.primary_price
    price_label = display.price_label

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


def prepare_product_cards(
    products: list[ComparisonProduct],
    web_steps: list[StepEvent] | None = None,
    top_recommendation: TopRecommendation | None = None,
) -> list[PreparedProductCard]:
    """Prepare the first six products without changing graph-owned order."""
    visible_products = products[:MAX_GRID_PRODUCTS]
    steps = web_steps or []
    first_identity = (
        canonical_product_key(visible_products[0]) if visible_products else ""
    )
    canonical_top = (
        top_recommendation
        if first_identity
        and top_recommendation is not None
        and top_recommendation.product_key == first_identity
        else None
    )
    return [
        PreparedProductCard(
            index=index,
            product=product,
            display=product_display(product),
            web_step=steps[index] if index < len(steps) else None,
            top_recommendation=canonical_top if index == 0 else None,
        )
        for index, product in enumerate(visible_products)
    ]


def shopping_grid_html(
    products: list[ComparisonProduct],
    web_steps: list[StepEvent] | None = None,
    top_recommendation: TopRecommendation | None = None,
) -> str:
    """Render up to six product cards in one responsive shopping grid."""
    cards = [
        product_card_html(
            prepared.product,
            prepared.web_step,
            prepared.top_recommendation,
        )
        for prepared in prepare_product_cards(
            products,
            web_steps,
            top_recommendation,
        )
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
        display = product_display(product)
        catalog_price = (
            private.price_low
            if private is not None and private.price_low is not None
            else private.price
            if private is not None
            else None
        )
        rows.append(
            {
                "Product": display.title,
                "Sources": " + ".join(display.source_labels),
                "Price shown": display.formatted_price,
                "Price source": display.price_label,
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
