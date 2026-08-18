"""LLM-assisted choices constrained to catalog-backed options and evidence."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from contracts import ComparisonProduct
from graph.llm import get_llm, load_prompt


DirectionId = Literal[
    "puzzle",
    "family_game",
    "craft_kit",
    "home_storage",
    "outdoor_basketball",
]


@dataclass(frozen=True)
class ShoppingDirection:
    option_id: DirectionId
    query: str
    category: str
    label: str
    selected_by: Literal["llm", "fallback"]


class _DirectionSelection(BaseModel):
    option_id: DirectionId


class _ProductSelection(BaseModel):
    candidate_number: int = Field(ge=1)


_DIRECTIONS: tuple[ShoppingDirection, ...] = (
    ShoppingDirection(
        option_id="puzzle",
        query="puzzle",
        category="Toys & Games",
        label="a puzzle",
        selected_by="fallback",
    ),
    ShoppingDirection(
        option_id="family_game",
        query="game",
        category="Toys & Games",
        label="a family game",
        selected_by="fallback",
    ),
    ShoppingDirection(
        option_id="craft_kit",
        query="craft kit",
        category="Toys & Games",
        label="a creative craft kit",
        selected_by="fallback",
    ),
    ShoppingDirection(
        option_id="home_storage",
        query="storage",
        category="Home & Kitchen",
        label="a useful home-storage item",
        selected_by="fallback",
    ),
    ShoppingDirection(
        option_id="outdoor_basketball",
        query="basketball",
        category="Sports & Outdoors",
        label="an outdoor basketball item",
        selected_by="fallback",
    ),
)


def _eligible_directions(context: dict) -> tuple[ShoppingDirection, ...]:
    avoided = {
        str(value).strip().casefold()
        for value in (context.get("avoid_categories") or [])
        if str(value).strip()
    }
    eligible = tuple(
        option
        for option in _DIRECTIONS
        if option.category.casefold() not in avoided
    )
    return eligible or _DIRECTIONS


async def choose_direction(
    transcript: str,
    dialogue_context: dict | None = None,
    *,
    llm_factory=get_llm,
) -> ShoppingDirection:
    """Let the configured LLM choose only among verified search directions."""
    context = dialogue_context or {}
    eligible = _eligible_directions(context)
    option_lines = "\n".join(
        f"- {option.option_id}: {option.label} "
        f"(query={option.query!r}, category={option.category!r})"
        for option in eligible
    )
    prior_request = str(context.get("previous_request") or "").strip()
    budget_max = context.get("budget_max")
    human = (
        "<shopper_turn>\n"
        f"{transcript}\n"
        "</shopper_turn>\n"
        "<prior_request>\n"
        f"{prior_request or 'none'}\n"
        "</prior_request>\n"
        f"Budget maximum: {budget_max if budget_max is not None else 'not stated'}\n"
        "Eligible catalog-backed options:\n"
        f"{option_lines}"
    )
    selected_id: str | None = None
    selected_by: Literal["llm", "fallback"] = "fallback"
    try:
        llm = llm_factory().with_structured_output(_DirectionSelection)
        selection = await asyncio.wait_for(
            llm.ainvoke(
                [("system", load_prompt("decision")), ("human", human)]
            ),
            timeout=max(0.5, float(os.getenv("DECISION_LLM_TIMEOUT_S", "6.0"))),
        )
        selected_id = selection.option_id
        selected_by = "llm"
    except Exception:
        # Product discovery must still work when the configured model is
        # temporarily unavailable. The fallback remains catalog-backed.
        selected_id = None

    selected = next(
        (option for option in eligible if option.option_id == selected_id),
        eligible[0],
    )
    return ShoppingDirection(
        option_id=selected.option_id,
        query=selected.query,
        category=selected.category,
        label=selected.label,
        selected_by=selected_by if selected.option_id == selected_id else "fallback",
    )


async def choose_product_index(
    transcript: str,
    products: list[ComparisonProduct],
    *,
    llm_factory=get_llm,
) -> tuple[int, Literal["llm", "fallback"]]:
    """Choose one prior grounded candidate; the model returns only its number."""
    if not products:
        raise ValueError("products must not be empty")
    candidate_lines = []
    for index, product in enumerate(products, 1):
        private = product.private
        live = product.live
        title = live.title if live is not None else private.title if private else "Product"
        catalog_price = private.price_low if private is not None else None
        web_price = live.price if live is not None else None
        live_rating = live.rating if live is not None else None
        candidate_lines.append(
            f"{index}. title={title!r}; catalog_price={catalog_price!r}; "
            f"web_price={web_price!r}; live_rating={live_rating!r}"
        )
    human = (
        "The shopper asked you to decide among these already grounded results.\n"
        "<shopper_turn>\n"
        f"{transcript}\n"
        "</shopper_turn>\n"
        "<candidates>\n"
        + "\n".join(candidate_lines)
        + "\n</candidates>\n"
        "Return the number of the strongest overall fit."
    )
    try:
        llm = llm_factory().with_structured_output(_ProductSelection)
        selection = await asyncio.wait_for(
            llm.ainvoke(
                [("system", load_prompt("decision")), ("human", human)]
            ),
            timeout=max(0.5, float(os.getenv("DECISION_LLM_TIMEOUT_S", "6.0"))),
        )
        index = int(selection.candidate_number) - 1
        if 0 <= index < len(products):
            return index, "llm"
    except Exception:
        pass
    return 0, "fallback"
