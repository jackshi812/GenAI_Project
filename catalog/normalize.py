"""Normalize the cleaned Amazon 2020 CSV into catalog records and Parquet."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = REPO_ROOT / "dataset" / "amazon_product_data_cleaned.csv"
DEFAULT_PARQUET_PATH = Path(__file__).resolve().parent / "products.parquet"

_RANGE_PRICE = re.compile(r"\$\s*([\d,]+\.\d{2})\s*-\s*\$\s*([\d,]+\.\d{2})")
_SPACED_CENTS_PRICE = re.compile(r"\$\s*([\d,]+)\s+(\d{2})\b")
_PLAIN_PRICE = re.compile(r"\$\s*([\d,]+\.\d{2})")
_BRAND_SPLIT = re.compile(r"[,\-(]")
_GENERIC_BRAND_OPENERS = {
    "the",
    "new",
    "set",
    "pack",
    "pcs",
    "mens",
    "womens",
    "kids",
}


def _text(value: Any) -> str:
    """Return a stripped string while treating pandas nulls as empty."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def parse_price(raw: Any) -> tuple[float | None, float | None, str]:
    """Parse catalog/Serper price text while preserving the original text."""
    raw_text = _text(raw)
    for pattern_name, pattern in (
        ("range", _RANGE_PRICE),
        ("spaced", _SPACED_CENTS_PRICE),
        ("plain", _PLAIN_PRICE),
    ):
        match = pattern.search(raw_text)
        if not match:
            continue
        if pattern_name == "range":
            low = float(match.group(1).replace(",", ""))
            high = float(match.group(2).replace(",", ""))
            return (min(low, high), max(low, high), raw_text)
        if pattern_name == "spaced":
            value = float(f"{match.group(1).replace(',', '')}.{match.group(2)}")
            return value, value, raw_text
        value = float(match.group(1).replace(",", ""))
        return value, value, raw_text
    return None, None, raw_text


def derive_brand(title: Any) -> str | None:
    """Derive only a conservative first-token brand candidate from a title."""
    title_text = _text(title)
    if not title_text:
        return None
    prefix = _BRAND_SPLIT.split(title_text, maxsplit=1)[0].strip()
    if not prefix:
        return None
    token = prefix.split()[0].rstrip(".,:;!?®™©'\"")
    lowered = token.lower()
    if (
        len(token) < 2
        or token[0].isdigit()
        or token.islower()
        or lowered in _GENERIC_BRAND_OPENERS
    ):
        return None
    return token or None


def top_category(category: Any) -> str | None:
    """Return the first segment of a pipe-delimited category hierarchy."""
    category_text = _text(category)
    if not category_text:
        return None
    value = category_text.split("|", maxsplit=1)[0].strip()
    return value or None


def first_image(image_field: Any) -> str | None:
    """Return the first image URL from a pipe-delimited field."""
    image_text = _text(image_field)
    if not image_text:
        return None
    value = image_text.split("|", maxsplit=1)[0].strip()
    return value or None


def load_products(csv_path: str | Path = DEFAULT_CSV_PATH) -> list[dict[str, Any]]:
    """Load all products as normalized plain dictionaries."""
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=True)
    products: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        sku = _text(row.get("Uniq Id"))
        title = _text(row.get("Product Name"))
        category_path = _text(row.get("Category"))
        price_low, price_high, price_raw = parse_price(row.get("Selling Price"))
        products.append(
            {
                "sku": sku,
                "doc_id": f"AMZ-{sku[:8].upper()}",
                "title": title,
                "description": _text(row.get("About Product")),
                "technical_details": _text(row.get("Technical Details")),
                "brand": derive_brand(title),
                "category": top_category(category_path),
                "category_path": category_path,
                "price_low": price_low,
                "price_high": price_high,
                "price_raw": price_raw,
                "image_url": first_image(row.get("Image")),
                "product_url": _text(row.get("Product Url")) or None,
            }
        )

    doc_ids = [product["doc_id"] for product in products]
    assert len(doc_ids) == len(set(doc_ids)), (
        "Short doc_id collision detected; widen the Uniq Id prefix to 12 characters."
    )
    return products


def write_products_parquet(
    products: list[dict[str, Any]],
    output_path: str | Path = DEFAULT_PARQUET_PATH,
) -> Path:
    """Write the assignment's named products.parquet artifact."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for product in products:
        feature_parts = [
            part
            for part in (
                product["description"],
                product["technical_details"],
            )
            if part
        ]
        records.append(
            {
                "id": product["sku"],
                "title": product["title"],
                "brand": product["brand"],
                "category": product["category"],
                "price": product["price_low"],
                "rating": None,
                "features": "\n".join(feature_parts),
                "ingredients": None,
            }
        )
    pd.DataFrame.from_records(records).to_parquet(output, engine="pyarrow", index=False)
    return output


def _sample_records(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = next(
        product
        for product in products
        if product["price_low"] is not None
        and product["price_low"] == product["price_high"]
    )
    ranged = next(
        product
        for product in products
        if product["price_low"] is not None
        and product["price_high"] is not None
        and not math.isclose(product["price_low"], product["price_high"])
    )
    failed = next(
        product
        for product in products
        if product["price_low"] is None and product["price_raw"]
    )
    return [clean, ranged, failed]


def main() -> None:
    products = load_products()
    parquet_path = write_products_parquet(products)
    numeric_count = sum(p["price_low"] is not None for p in products)
    brand_count = sum(p["brand"] is not None for p in products)
    categories = Counter(p["category"] for p in products if p["category"])

    print(f"total_rows: {len(products)}")
    print(f"numeric_price_rows: {numeric_count}")
    print(f"unparsed_or_blank_price_rows: {len(products) - numeric_count}")
    print(f"resolved_brand_rows: {brand_count}")
    print(f"top_categories: {categories.most_common(5)}")
    print(f"parquet: {parquet_path}")
    print("sample_records:")
    print(json.dumps(_sample_records(products), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
