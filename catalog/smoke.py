"""Runnable retrieval checks and canonical-query evidence capture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from catalog.normalize import load_products
from catalog.search import search

CANONICAL_PATH = Path(__file__).resolve().parent / "canonical_queries.json"


def _print_results(label: str, results: list[dict[str, Any]]) -> None:
    print(f"\n## {label}")
    print(json.dumps(results, indent=2, ensure_ascii=False))


def main() -> None:
    budget = search("500 piece jigsaw puzzle", price_max=20.0)
    assert budget and all(
        item["price_low"] is not None and item["price_low"] <= 20.0 for item in budget
    )
    _print_results("budget filter: price_max=20", budget)

    unfiltered = search("500 piece jigsaw puzzle", k=20)
    assert any(
        item["price_low"] is not None and item["price_low"] > 20.0
        for item in unfiltered
    )
    _print_results("same semantics, no budget filter", unfiltered)

    combined = search(
        "500 piece jigsaw puzzle",
        price_max=20.0,
        category="Toys & Games",
    )
    assert combined and all(item["category"] == "Toys & Games" for item in combined)
    _print_results("combined category and budget filters", combined)

    dirty = next(
        product
        for product in load_products()
        if product["price_low"] is None and product["price_raw"]
    )
    dirty_results = search(dirty["title"], k=10)
    assert dirty["doc_id"] in {item["doc_id"] for item in dirty_results}
    _print_results(f"unparseable price title: {dirty['title']}", dirty_results)

    canonical = json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))
    print("\n## canonical expected-ID checks")
    for item in canonical:
        filters = {**item["filters"], "k": 5}
        results = search(item["semantic_query"], **filters)
        expected = set(item["expected_doc_ids"])
        returned = {result["doc_id"] for result in results}
        passed = expected.issubset(returned)
        print(
            json.dumps(
                {
                    "id": item["id"],
                    "expected_doc_ids": sorted(expected),
                    "returned_doc_ids": sorted(returned),
                    "status": "PASS" if passed else "FAIL",
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        assert passed, f"canonical query failed: {item['id']}"


if __name__ == "__main__":
    main()
