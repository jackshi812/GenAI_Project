"""Build the persistent Chroma index for the private Amazon catalog."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import chromadb

from catalog.normalize import DEFAULT_CSV_PATH, load_products

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHROMA_PATH = REPO_ROOT / "catalog" / "chroma"
COLLECTION_NAME = "products"
BATCH_SIZE = 500


def chroma_path() -> Path:
    configured = os.getenv("CHROMA_PATH")
    return Path(configured) if configured else DEFAULT_CHROMA_PATH


def document_text(product: dict[str, Any]) -> str:
    """Compose bounded embedding text from title and actual catalog features."""
    base = f"{product['title']}\n\n{product['description']}".strip()
    technical = product["technical_details"]
    if technical and len(base) + len(technical) + 2 <= 2_000:
        base = f"{base}\n\n{technical}"
    return base[:2_000]


def metadata(product: dict[str, Any]) -> dict[str, str | float]:
    """Convert a product to Chroma metadata, omitting unsupported nulls."""
    result: dict[str, str | float] = {
        "sku": product["sku"],
        "doc_id": product["doc_id"],
        "title": product["title"],
        "price_raw": product["price_raw"],
    }
    for key in (
        "brand",
        "category",
        "category_path",
        "image_url",
        "product_url",
        "price_low",
        "price_high",
    ):
        value = product[key]
        if value is not None:
            result[key] = value
    return result


def build_index() -> int:
    products = load_products(DEFAULT_CSV_PATH)
    path = chroma_path()
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(path))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception as exc:
        if (
            "does not exist" not in str(exc).lower()
            and "not found" not in str(exc).lower()
        ):
            raise
    collection = client.create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    for start in range(0, len(products), BATCH_SIZE):
        batch = products[start : start + BATCH_SIZE]
        collection.add(
            ids=[product["sku"] for product in batch],
            documents=[document_text(product) for product in batch],
            metadatas=[metadata(product) for product in batch],
        )
        print(f"indexed {min(start + len(batch), len(products))}/{len(products)}")

    count = collection.count()
    print(f"final_count: {count}")
    return count


if __name__ == "__main__":
    build_index()
