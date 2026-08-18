"""Hybrid semantic and metadata-filtered search over the private catalog."""

from __future__ import annotations

import re
from typing import Any

import chromadb

from catalog.build_index import COLLECTION_NAME, chroma_path


def _where_clause(
    price_max: float | None,
    price_min: float | None,
    category: str | None,
    brand: str | None,
) -> dict[str, Any] | None:
    conditions: list[dict[str, Any]] = []
    if price_max is not None:
        conditions.append({"price_low": {"$lte": float(price_max)}})
    if price_min is not None:
        conditions.append({"price_low": {"$gte": float(price_min)}})
    if category:
        conditions.append({"category": {"$eq": category}})
    if brand:
        conditions.append({"brand": {"$eq": brand}})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _budget_fit(metadata: dict[str, Any], price_max: float | None) -> str:
    if price_max is None:
        return "unknown"
    low = metadata.get("price_low")
    high = metadata.get("price_high")
    if low is None:
        return "unknown"
    if high is None or float(high) <= float(price_max):
        return "within"
    return "partial"


def _terms(text: str) -> set[str]:
    """Normalize lightweight lexical terms, including comma-formatted numbers."""
    normalized = re.sub(
        r"\b\d[\d,]*\b",
        lambda match: match.group(0).replace(",", ""),
        text.lower(),
    )
    terms = set(re.findall(r"[a-z0-9]+", normalized))
    return {
        term[:-1] if term.endswith("s") and len(term) > 3 else term for term in terms
    }


_FEATURE_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "i",
    "is",
    "it",
    "me",
    "of",
    "or",
    "the",
    "to",
    "with",
}
_BOILERPLATE = re.compile(
    r"(?:make sure this fits|go to your orders|return shipping label|"
    r"show up to \d+ reviews|product description|"
    r"\b\d(?:\.\d)?\s*(?:out of 5|stars?)\b)",
    re.IGNORECASE,
)


def _feature_segments(document: str, title: str) -> list[str]:
    """Split real catalog detail text into bounded, useful evidence excerpts."""
    detail = str(document or "").strip()
    if detail.casefold().startswith(title.casefold()):
        detail = detail[len(title) :].lstrip()
    raw_segments = re.split(r"\s*\|\s*|\n+|(?<=[.!?])\s+", detail)
    segments: list[str] = []
    seen: set[str] = set()
    for raw in raw_segments:
        segment = re.sub(r"\s+", " ", raw).strip(" -•\t")
        key = segment.casefold()
        if (
            len(segment) < 8
            or key in seen
            or _BOILERPLATE.search(segment)
        ):
            continue
        seen.add(key)
        if len(segment) > 220:
            segment = segment[:217].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
        segments.append(segment)
    return segments


def _feature_evidence(query: str, document: str, title: str) -> list[str]:
    """Return only query-relevant excerpts copied from catalog source text."""
    query_terms = _terms(query) - _FEATURE_STOPWORDS
    ranked: list[tuple[float, int, str]] = []
    for index, segment in enumerate(_feature_segments(document, title)):
        segment_terms = _terms(segment)
        overlap = len(query_terms & segment_terms)
        if not overlap:
            continue
        coverage = overlap / max(len(query_terms), 1)
        ranked.append((coverage + (0.08 * overlap), -index, segment))
    ranked.sort(reverse=True)
    return [segment for _, _, segment in ranked[:3]]


def _rank_score(
    query: str,
    title: str,
    document: str,
    similarity: float,
) -> float:
    """Rerank vectors using title and grounded feature-term coverage."""
    query_terms = _terms(query)
    title_terms = _terms(title)
    document_terms = _terms(document)
    title_coverage = len(query_terms & title_terms) / max(len(query_terms), 1)
    evidence_coverage = len(query_terms & document_terms) / max(len(query_terms), 1)
    query_numbers = {term for term in query_terms if term.isdigit()}
    missing_number_penalty = (
        0.75 if query_numbers and not query_numbers.issubset(document_terms) else 0.0
    )
    return (
        similarity
        + (0.25 * title_coverage)
        + (0.35 * evidence_coverage)
        - missing_number_penalty
    )


def search(
    query: str,
    price_max: float | None = None,
    price_min: float | None = None,
    category: str | None = None,
    brand: str | None = None,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Search product meaning semantically and apply constraints as metadata."""
    semantic_query = str(query).strip()
    if not semantic_query:
        raise ValueError("query must be a non-empty string")
    if price_max is not None and price_min is not None and price_min > price_max:
        raise ValueError("price_min cannot be greater than price_max")
    result_limit = max(1, min(int(k), 50))

    client = chromadb.PersistentClient(path=str(chroma_path()))
    collection = client.get_collection(COLLECTION_NAME)
    where = _where_clause(price_max, price_min, category, brand)
    query_args: dict[str, Any] = {
        "query_texts": [semantic_query],
        # Retrieve a wider semantic pool, then use a transparent lexical/count
        # rerank. MiniLM alone often treats 500- and 1,000-piece puzzles as
        # interchangeable even though count is a material product variant.
        "n_results": min(max(result_limit * 10, 50), 200),
        "include": ["metadatas", "distances", "documents"],
    }
    if where is not None:
        query_args["where"] = where
    response = collection.query(**query_args)

    metadatas = (response.get("metadatas") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]
    documents = (response.get("documents") or [[]])[0]
    results: list[dict[str, Any]] = []
    for item, distance, document in zip(
        metadatas,
        distances,
        documents,
        strict=True,
    ):
        price_low = item.get("price_low")
        similarity = round(1.0 - float(distance), 6)
        document_text = str(document or item["title"])
        result = {
            "sku": item["sku"],
            "title": item["title"],
            "price": price_low if price_low is not None else item.get("price_raw", ""),
            "rating": None,
            "brand": item.get("brand"),
            "ingredients": None,
            "doc_id": item["doc_id"],
            "image_url": item.get("image_url"),
            "product_url": item.get("product_url"),
            "category": item.get("category"),
            "price_low": price_low,
            "price_high": item.get("price_high"),
            "similarity": similarity,
            "budget_fit": _budget_fit(item, price_max),
            "feature_evidence": _feature_evidence(
                semantic_query,
                document_text,
                item["title"],
            ),
            "_rank_score": _rank_score(
                semantic_query,
                item["title"],
                document_text,
                similarity,
            ),
        }
        results.append(result)

    budget_rank = {"within": 0, "partial": 1, "unknown": 2}
    results.sort(
        key=lambda item: (budget_rank[item["budget_fit"]], -item["_rank_score"])
    )
    for item in results:
        item.pop("_rank_score")
    return results[:result_limit]
