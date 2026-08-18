"""Shared validated result shapes for the catalog, graph, and interface."""

from __future__ import annotations

import re
from typing import Any as _Any
from typing import Literal as _Literal

from pydantic import BaseModel as _BaseModel
from pydantic import ConfigDict as _ConfigDict
from pydantic import Field as _Field
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
    # Query-relevant excerpts copied from the catalog's real About Product /
    # Technical Details fields. These are the only catalog feature claims the
    # response layer may make beyond facts stated in the title.
    feature_evidence: list[str] = _Field(default_factory=list)

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

    # Additive UI metadata supplied by Serper Shopping when available.
    image_url: str | None = None

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
    """A catalog/live comparison, including honest web-only fallback results."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    private: RagResult | None
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


class TopRecommendation(_BaseModel):
    """Canonical graph-owned recommendation rendered consistently by the UI."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    # ``catalog:{doc_id}`` when private evidence exists, otherwise
    # ``live:{url}``. The graph keeps this key aligned with products[0].
    product_key: str
    title: str
    reason: str


class ShoppingContext(_BaseModel):
    """Conversation-safe shopping preferences carried between turns.

    The profile contains only shopper-stated or explicitly inferred search
    requirements. Product facts never enter this model; those still come from
    ``RagResult`` / ``WebResult`` evidence.
    """

    model_config = _ConfigDict(strict=True, extra="forbid")

    product_query: str = ""
    colors: list[str] = _Field(default_factory=list)
    sizes: list[str] = _Field(default_factory=list)
    materials: list[str] = _Field(default_factory=list)
    textures: list[str] = _Field(default_factory=list)
    comfort: list[str] = _Field(default_factory=list)
    features: list[str] = _Field(default_factory=list)
    excluded: list[str] = _Field(default_factory=list)
    resolved_query: str = ""
    is_followup: bool = False
    preference_changed: bool = False
    understanding_source: _Literal["rules", "llm", "fallback"] = "rules"


class AssistantResult(_BaseModel):
    """The graph-to-interface response contract."""

    model_config = _ConfigDict(strict=True, extra="forbid")

    transcript: str
    plan: str | None
    answer_text: str
    products: list[ComparisonProduct]
    steps: list[StepEvent]
    citations: list[Citation]
    top_recommendation: TopRecommendation | None = None
    shopping_context: ShoppingContext | None = None
