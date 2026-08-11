"""Fixture-backed implementation of the ToolClient seam.

Reads Jack's `fixtures.json` at the repository root. Expected structure
(coordinate any change through Jack):

    {
      "rag_results": { "<eight-word key>": [ {RagResult...}, ... ] },
      "web_results": { "<eight-word key>": [ {WebResult...}, ... ] },
      "transcripts": [ "..." ]
    }

`rag_results` may alternatively be a flat list; then it is used for every
query with filters applied locally. Lookup is exact-match on the shared
eight-word key (D-08) — a miss returns an empty list with a one-line warning,
never a fuzzy neighbour.

This client stays after live MCP integration as the recorded fallback.
"""

import json
import sys
from pathlib import Path

from contracts import RagResult, WebResult

from graph.tools import _decode, clean_filters, eight_word_key

_REPO_ROOT = Path(__file__).resolve().parents[1]


class FixtureTools:
    """Same lifecycle shape as the Phase 2 MCP client (async context manager),
    even though fixture reads are immediate."""

    def __init__(self, path: Path | None = None):
        self._path = path or (_REPO_ROOT / "fixtures.json")
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        self._rag = data.get("rag_results", {})
        # Jack keys web_results by full catalog title; the graph queries with
        # the D-08 eight-word key. Index both under the normalized eight-word
        # key so lookup stays exact-match either way (never fuzzy).
        raw_web = data.get("web_results", {})
        self._web = {eight_word_key(k): v for k, v in raw_web.items()}
        self._web.update({k: v for k, v in raw_web.items()})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def rag_search(self, query: str, **filters) -> list[RagResult]:
        filters = clean_filters(filters)
        if isinstance(self._rag, dict):
            payload = self._rag.get(eight_word_key(query))
            if payload is None:
                print(
                    f"[fixtures] rag.search miss for key {eight_word_key(query)!r}",
                    file=sys.stderr,
                )
                return []
        else:
            payload = self._rag
        results = _decode(payload, RagResult)
        results = self._apply_filters(results, filters)
        k = filters.get("k")
        return results[: int(k)] if k else results

    async def web_search(self, query: str, num: int = 10) -> list[WebResult]:
        payload = self._web.get(eight_word_key(query))
        if payload is None:
            print(
                f"[fixtures] web.search miss for key {eight_word_key(query)!r}",
                file=sys.stderr,
            )
            return []
        return _decode(payload, WebResult)[:num]

    @staticmethod
    def _apply_filters(results: list[RagResult], filters: dict) -> list[RagResult]:
        """Apply price/category/brand filters locally so the budget canonical
        query visibly does something in fixture mode. Products whose price
        could not be parsed (price_low is None) are kept: unparseable is not
        the same as over budget (RAG-06)."""
        out = []
        pmax = filters.get("price_max")
        pmin = filters.get("price_min")
        cat = filters.get("category")
        brand = filters.get("brand")
        for r in results:
            low = getattr(r, "price_low", None)
            high = getattr(r, "price_high", None)
            if pmax is not None and low is not None and low > float(pmax):
                continue
            if pmin is not None and high is not None and high < float(pmin):
                continue
            if cat and (getattr(r, "category", None) or "").lower() != str(cat).lower():
                continue
            if brand and (getattr(r, "brand", None) or "").lower() != str(brand).lower():
                continue
            out.append(r)
        return out
