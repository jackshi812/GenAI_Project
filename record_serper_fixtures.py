"""Record raw Serper Shopping responses for every canonical catalog product."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from catalog.normalize import load_products

REPO_ROOT = Path(__file__).resolve().parent
CANONICAL_PATH = REPO_ROOT / "catalog" / "canonical_queries.json"
OUTPUT_PATH = REPO_ROOT / "serper_fixtures.json"
SERPER_SHOPPING_URL = "https://google.serper.dev/shopping"


def fixture_key(query: str) -> str:
    """Return the replay key shared with the MCP web-search implementation."""
    return " ".join(str(query).split()[:8]).lower()


def canonical_products() -> list[dict[str, Any]]:
    """Resolve every unique canonical doc ID to its real catalog product."""
    canonical = json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))
    expected_ids = {
        doc_id
        for scenario in canonical
        for doc_id in scenario.get("expected_doc_ids", [])
    }
    products_by_id = {product["doc_id"]: product for product in load_products()}
    missing = sorted(expected_ids - products_by_id.keys())
    if missing:
        raise RuntimeError(f"Canonical doc IDs missing from catalog: {missing}")

    products = [products_by_id[doc_id] for doc_id in sorted(expected_ids)]
    keys = [fixture_key(product["title"]) for product in products]
    if len(keys) != len(set(keys)):
        raise RuntimeError("Canonical product titles collide under the fixture-key rule")
    return products


def record() -> dict[str, dict[str, Any]]:
    """Call Serper once per canonical product and return raw response objects."""
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SERPER_API_KEY is not set")

    products = canonical_products()
    captured: dict[str, dict[str, Any]] = {}
    for index, product in enumerate(products):
        query = product["title"]
        response = requests.post(
            SERPER_SHOPPING_URL,
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"q": query, "num": 10},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        shopping = payload.get("shopping") if isinstance(payload, dict) else None
        if not isinstance(shopping, list) or not shopping:
            raise RuntimeError(f"No Shopping results returned for: {query}")

        key = fixture_key(query)
        captured[key] = payload
        print(f"Captured {len(shopping)} results: {key}")
        if index < len(products) - 1:
            time.sleep(1.0)
    return captured


def write_fixtures(captured: dict[str, dict[str, Any]]) -> None:
    """Merge complete captures into the replay file using an atomic replace."""
    if OUTPUT_PATH.exists():
        fixtures = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        if not isinstance(fixtures, dict):
            raise RuntimeError("Existing serper_fixtures.json is not a JSON object")
    else:
        fixtures = {}

    fixtures.update(captured)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(fixtures, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT_PATH)
    print(f"Saved {OUTPUT_PATH.name} with {len(fixtures)} fixture keys")


def main() -> None:
    write_fixtures(record())


if __name__ == "__main__":
    main()
