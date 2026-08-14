"""Shared validated result shapes for the catalog, graph, and interface."""

from __future__ import annotations

import re
from typing import Any as _Any
from typing import Literal as _Literal

from pydantic import BaseModel as _BaseModel
from pydantic import ConfigDict as _ConfigDict
from pydantic import field_validator as _field_validator


class RagResult(_BaseModel):
    """One grounded result from the private 2020 Amazon catalog."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    # Assignment-mandated keys.
    sku: str
    title: str
    price: float | str
    rating: float | None
    brand: str | None
    ingredients: str | None
    doc_id: str

    # Additive UI and reconciliation keys.
    image_url: str
    product_url: str
    category: str | None
    price_low: float | None
    price_high: float | None
    similarity: float
    budget_fit: _Literal["within", "partial", "unknown"]

    @_field_validator("price")
    @classmethod
    def reject_numeric_price_strings(cls, value: float | str) -> float | str:
        """Keep raw, unparseable price text while rejecting serialized numbers."""
        if isinstance(value, str):
            candidate = value.strip().removeprefix("$").replace(",", "").strip()
            if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", candidate):
                raise ValueError("numeric prices must be JSON numbers, not strings")
        return value

    @_field_validator("rating")
    @classmethod
    def private_rating_must_be_absent(cls, value: float | None) -> None:
        if value is not None:
            raise ValueError("the private catalog has no rating data")
        return None

    @_field_validator("ingredients")
    @classmethod
    def private_ingredients_must_be_absent(cls, value: str | None) -> None:
        if value is not None:
            raise ValueError("the private catalog has no ingredient data")
        return None


class WebResult(_BaseModel):
    """One normalized Serper Shopping result."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    # Assignment-mandated keys.
    title: str
    url: str
    snippet: str
    price: float | str | None = None
    availability: str | None = None

    # Additive: live search is the only rating source in this project.
    rating: float | None = None

    # Additive provenance. ``unknown`` keeps older fixture/test payloads valid,
    # but the Phase 2 live acceptance gate rejects it.
    origin: _Literal["live_serper", "recorded_fixture", "unknown"] = "unknown"


class MatchInfo(_BaseModel):
    """Inspectable evidence for a private-to-live product match."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    similarity: float
    verdict: _Literal["same", "different", "unsure"]
    reason: str


class Conflict(_BaseModel):
    """A genuine disagreement between two known field values."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    field: str
    private_value: _Any
    live_value: _Any
    note: str


class ComparisonProduct(_BaseModel):
    """A catalog result plus its optional matched live evidence."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    private: RagResult
    live: WebResult | None
    conflicts: list[Conflict]
    match: MatchInfo | None


class StepEvent(_BaseModel):
    """One truthful, completed or failed agent step."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    node: str
    tool: str | None
    started_at: str
    duration_ms: int | None
    status: str
    detail: str


class Citation(_BaseModel):
    """A private document identifier or a live source link."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    kind: _Literal["private", "live"]
    label: str
    url: str | None


class AssistantResult(_BaseModel):
    """The graph-to-interface response contract."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    transcript: str
    plan: str | None
    answer_text: str
    products: list[ComparisonProduct]
    steps: list[StepEvent]
    citations: list[Citation]
