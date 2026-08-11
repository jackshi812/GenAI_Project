"""Serper Shopping search with exact fixture replay and safety controls."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from catalog.normalize import parse_price

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "serper_fixtures.json"
LOG_PATH = Path(__file__).resolve().parent / "logs" / "mcp.jsonl"
SERPER_SHOPPING_URL = "https://google.serper.dev/shopping"
ALLOWED_DOMAINS = (
    "amazon.com",
    "walmart.com",
    "target.com",
    "bestbuy.com",
    "ebay.com",
    "etsy.com",
    "chewy.com",
    "homedepot.com",
    "lowes.com",
    "costco.com",
    "newegg.com",
    "wayfair.com",
)

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_STATE_LOCK = threading.Lock()
_LAST_LIVE_CALL = 0.0
_LIVE_CALLS = 0


def _utc_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _log_event(event: str, **details: Any) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = {"timestamp": _utc_timestamp(), "direction": "event", "event": event}
    line.update(details)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def normalized_query(query: str) -> str:
    return " ".join(str(query).lower().split())


def fixture_key(query: str) -> str:
    return " ".join(str(query).split()[:8]).lower()


def _allowed_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return False
    return any(
        host == domain or host.endswith(f".{domain}") for domain in ALLOWED_DOMAINS
    )


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    low, _, _ = parse_price(text if "$" in text else f"${text}")
    return low


def normalize_response(raw_response: dict[str, Any], num: int) -> list[dict[str, Any]]:
    """Normalize live and recorded Serper shopping responses identically."""
    results: list[dict[str, Any]] = []
    dropped = 0
    for entry in raw_response.get("shopping", []):
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("link") or "").strip()
        if not _allowed_url(url):
            dropped += 1
            continue
        source = str(entry.get("source") or "").strip()
        delivery = str(entry.get("delivery") or "").strip()
        snippet = " · ".join(part for part in (source, delivery) if part)
        # `rating` is additive to the assignment's five-key web schema and is
        # the only rating source because the private catalog has none.
        results.append(
            {
                "title": str(entry.get("title") or "").strip(),
                "url": url,
                "snippet": snippet,
                "price": _float_or_none(entry.get("price")),
                "availability": delivery or None,
                "rating": _float_or_none(entry.get("rating")),
            }
        )
        if len(results) >= num:
            break
    if dropped:
        _log_event("allowlist_drop", count=dropped)
    return results


def _load_fixture(query: str) -> dict[str, Any] | None:
    key = fixture_key(query)
    if not FIXTURE_PATH.exists():
        _log_event("fixture_file_missing", fixture_id=key)
        return None
    try:
        fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log_event("fixture_file_error", error=type(exc).__name__)
        return None
    normalized_fixtures = {
        fixture_key(stored): value for stored, value in fixtures.items()
    }
    response = normalized_fixtures.get(key)
    if response is None:
        _log_event("fixture_miss", fixture_id=key)
        return None
    _log_event("fixture_replay", fixture_id=key)
    return response if isinstance(response, dict) else None


def _cache_ttl() -> int:
    return max(60, min(int(os.getenv("WEB_SEARCH_CACHE_TTL", "180")), 300))


def _call_serper(query: str, num: int, api_key: str) -> dict[str, Any] | None:
    global _LAST_LIVE_CALL, _LIVE_CALLS
    min_interval = max(0.0, float(os.getenv("WEB_SEARCH_MIN_INTERVAL_S", "1.0")))
    max_calls = max(1, int(os.getenv("WEB_SEARCH_MAX_CALLS", "50")))
    with _STATE_LOCK:
        if _LIVE_CALLS >= max_calls:
            _log_event("rate_limit_call_cap", max_calls=max_calls)
            return None
        elapsed = time.monotonic() - _LAST_LIVE_CALL
        sleep_seconds = max(0.0, min_interval - elapsed) if _LAST_LIVE_CALL else 0.0
        if sleep_seconds:
            _log_event("rate_limit_sleep", seconds=round(sleep_seconds, 3))
            time.sleep(sleep_seconds)
        else:
            _log_event("rate_limit_pass", seconds=0.0)
        _LAST_LIVE_CALL = time.monotonic()
        _LIVE_CALLS += 1

    # Retailer pages are never scraped. Serper's paid search API is the only
    # outbound service, which keeps retailer robots.txt/ToS outside this client.
    try:
        response = httpx.post(
            SERPER_SHOPPING_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        _log_event("serper_error", error=type(exc).__name__)
        return None


def web_search(query: str, num: int = 10) -> list[dict[str, Any]]:
    """Search Serper Shopping, or replay an exact recorded response without a key."""
    query_text = str(query).strip()
    if not query_text:
        raise ValueError("query must be a non-empty string")
    result_limit = max(1, min(int(num), 20))
    cache_key = f"{normalized_query(query_text)}|{result_limit}"
    now = time.monotonic()
    with _STATE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] > now:
            _log_event("cache", cache="hit", query=normalized_query(query_text))
            return [dict(item) for item in cached[1]]
        if cached:
            _CACHE.pop(cache_key, None)

    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if api_key:
        raw_response = _call_serper(query_text, result_limit, api_key)
        if raw_response is None:
            _log_event("live_fallback_to_fixture", query=normalized_query(query_text))
            raw_response = _load_fixture(query_text)
    else:
        raw_response = _load_fixture(query_text)
    results = normalize_response(raw_response or {}, result_limit)
    with _STATE_LOCK:
        _CACHE[cache_key] = (time.monotonic() + _cache_ttl(), results)
    return [dict(item) for item in results]
