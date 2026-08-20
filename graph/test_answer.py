"""Regression tests for Answerer/Critic citation completeness."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from contracts import (
    ComparisonProduct,
    MatchInfo,
    RagResult,
    ShoppingContext,
    TopRecommendation,
    WebResult,
)
from graph.answer import (
    AnswerOutput,
    CriticOutput,
    _answer_call,
    _canonical_answer_text,
    _critic_issues,
    _degraded_answer,
    answerer_node,
    natural_answer_once,
)
from graph.recommendation import build_top_recommendation


LIVE_URL = "https://www.example.com/widget-alpha"


def _product() -> ComparisonProduct:
    private = RagResult(
        sku="widget-alpha",
        title="Widget Alpha",
        price=10.0,
        rating=None,
        brand="Widget",
        ingredients=None,
        doc_id="AMZ-WIDGET01",
        image_url="https://www.example.com/widget.jpg",
        product_url="https://www.example.com/catalog/widget-alpha",
        category="Test",
        price_low=10.0,
        price_high=10.0,
        similarity=0.9,
        budget_fit="unknown",
    )
    live = WebResult(
        title="Widget Alpha",
        url=LIVE_URL,
        snippet="Example retailer listing",
        price=21.95,
        availability="in stock",
        rating=4.5,
    )
    return ComparisonProduct(
        private=private,
        live=live,
        conflicts=[],
        match=MatchInfo(similarity=1.0, verdict="same", reason="Exact title match"),
    )


def _draft(*, include_live_url: bool) -> AnswerOutput:
    return AnswerOutput(
        answer_text="Widget Alpha has a live price of $21.95; details are on screen.",
        cited_doc_ids=["AMZ-WIDGET01"],
        cited_urls=[LIVE_URL] if include_live_url else [],
    )


class CitationCompletenessTests(unittest.IsolatedAsyncioTestCase):
    def test_deterministic_answer_uses_the_retrieved_matched_detail(self) -> None:
        detail = "Soft padded grip designed for comfortable play"
        product = _product().model_copy(
            update={
                "private": _product().private.model_copy(
                    update={"feature_evidence": [detail]}
                ),
                "live": None,
                "match": None,
            },
            deep=True,
        )
        state = {
            "transcript": "Find a comfortable widget under $20",
            "semantic_query": "comfortable widget",
            "constraints": {"budget_max": 20.0},
            "products": [product],
        }

        top = build_top_recommendation([product], state)
        draft = _degraded_answer([product], state)

        self.assertEqual(top.reason, f"Catalog evidence notes: {detail}.")
        self.assertIn(detail, draft.answer_text)

    def test_long_enumerated_detail_ends_at_a_complete_clause(self) -> None:
        detail = (
            "The latest line of Barbie Fashionistas dolls includes 7 body "
            "types, 9 skin tones, 35 hairstyles and countless fashions"
        )
        product = _product().model_copy(
            update={
                "private": _product().private.model_copy(
                    update={"feature_evidence": [detail]}
                ),
                "live": None,
                "match": None,
            },
            deep=True,
        )
        state = {
            "transcript": "Find a Barbie doll",
            "semantic_query": "Barbie doll",
            "products": [product],
        }

        top = build_top_recommendation([product], state)
        draft = _degraded_answer([product], state)

        complete_reason = (
            "Catalog evidence notes: The latest line of Barbie Fashionistas "
            "dolls includes 7 body types."
        )
        self.assertEqual(top.reason, complete_reason)
        self.assertTrue(draft.answer_text.endswith(complete_reason))
        self.assertLessEqual(len(draft.answer_text.split()), 30)

    def test_short_feature_detail_keeps_complete_open_ended_play_clause(self) -> None:
        detail = (
            "Features a mix of bright, colorful LEGO pieces that allow for "
            "open-ended play."
        )
        product = _product().model_copy(
            update={
                "private": _product().private.model_copy(
                    update={
                        "title": "LEGO Classic Creative Brick Box Set",
                        "feature_evidence": [detail],
                    }
                ),
                "live": None,
                "match": None,
            },
            deep=True,
        )
        state = {
            "transcript": "Find LEGO for my kid",
            "semantic_query": "LEGO",
            "products": [product],
        }

        top = build_top_recommendation([product], state)
        draft = _degraded_answer([product], state)

        complete_reason = f"Catalog evidence notes: {detail}"
        self.assertEqual(top.reason, complete_reason)
        self.assertTrue(draft.answer_text.endswith(complete_reason))
        self.assertLessEqual(len(draft.answer_text.split()), 30)

    def test_long_punctuation_free_detail_falls_back_to_grounded_reason(self) -> None:
        detail = (
            "Designed with bright colorful reusable building pieces that encourage "
            "imaginative collaborative creative play for children across many open "
            "ended projects at home"
        )
        product = _product().model_copy(
            update={
                "private": _product().private.model_copy(
                    update={"feature_evidence": [detail]}
                ),
                "live": None,
                "match": None,
            },
            deep=True,
        )
        state = {
            "transcript": "Find a building toy",
            "semantic_query": "building toy",
            "products": [product],
        }

        top = build_top_recommendation([product], state)

        self.assertEqual(top.reason, "Its 2020 catalog price is $10.00.")
        self.assertNotIn("Designed with", top.reason)

    def test_canonical_opening_reserves_room_for_complete_reason(self) -> None:
        reason = (
            "Catalog evidence notes: one two three four five six seven eight nine "
            "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen "
            "nineteen."
        )
        canonical = TopRecommendation(
            product_key="catalog:OPENING-1",
            title="Alpha Beta Gamma Delta Epsilon",
            reason=reason,
        )

        answer = _canonical_answer_text(canonical)

        self.assertTrue(answer.endswith(reason))
        self.assertLessEqual(len(answer.split()), 30)

    def test_canonical_answer_without_a_reason_does_not_add_generic_fit_filler(self) -> None:
        canonical = TopRecommendation(
            product_key="catalog:WILDKIN",
            title="Wildkin Kids Overnighter Duffel Bag for Boys and Girls",
            reason="",
        )

        answer = _canonical_answer_text(canonical)

        self.assertTrue(answer.startswith("I found Wildkin Kids"))
        self.assertEqual(answer, answer.strip())
        self.assertNotIn("grounded option", answer.casefold())
        self.assertNotIn("request", answer.casefold())

    def test_canonical_title_matches_the_live_title_shown_by_the_card(self) -> None:
        product = _product()
        product = product.model_copy(
            update={
                "live": product.live.model_copy(
                    update={"title": "Widget Alpha Current Listing"}
                )
            },
            deep=True,
        )

        top = build_top_recommendation(
            [product],
            {"semantic_query": "widget", "products": [product]},
        )

        self.assertEqual(top.title, "Widget Alpha Current Listing")
        self.assertEqual(top.product_key, "catalog:AMZ-WIDGET01")

    async def test_one_call_rejects_canned_query_echo_as_match_reason(self) -> None:
        product = _product().model_copy(
            update={
                "live": _product().live.model_copy(
                    update={"origin": "live_serper"}
                )
            },
            deep=True,
        )
        state = {
            "transcript": "Compare the options",
            "semantic_query": "widget",
            "plan": "Compare grounded evidence.",
        }
        rationales = (
            "It matches your widget request.",
            "It fits your widget request.",
            "It is the closest grounded candidate for your widget request.",
            "It is the highest-ranked grounded match for your widget request.",
        )
        for rationale in rationales:
            with self.subTest(rationale=rationale):
                draft = AnswerOutput(
                    answer_text=(
                        "Widget Alpha currently costs $21.95 and is in stock. "
                        + rationale
                    ),
                    cited_doc_ids=["AMZ-WIDGET01"],
                    cited_urls=[LIVE_URL],
                )
                with patch.dict(
                    "os.environ",
                    {
                        "NATURAL_RESPONSE_LLM": "1",
                        "LLM_PROVIDER": "anthropic",
                        "ANTHROPIC_API_KEY": "test-key",
                    },
                    clear=False,
                ), patch(
                    "graph.answer._answer_call",
                    new=AsyncMock(return_value=draft),
                ):
                    result = await natural_answer_once(state, [product])

                self.assertIsNone(result)

    async def test_one_call_accepts_grounded_feature_paraphrase(self) -> None:
        product = _product().model_copy(
            update={
                "private": _product().private.model_copy(
                    update={
                        "feature_evidence": [
                            "Blue canvas exterior with padded shoulder straps"
                        ]
                    }
                ),
                "live": None,
                "match": None,
            },
            deep=True,
        )
        draft = AnswerOutput(
            answer_text=(
                "I’d recommend Widget Alpha first: its blue canvas exterior and "
                "padded shoulder straps stand out."
            ),
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[],
        )
        state = {
            "transcript": "Find a blue canvas widget with padded straps",
            "semantic_query": "widget",
            "plan": "Use grounded evidence.",
        }
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(state, [product])

        self.assertEqual(result, draft)

    async def test_one_call_rejects_invented_feature_even_with_exact_reason(self) -> None:
        product = _product().model_copy(
            update={
                "private": _product().private.model_copy(
                    update={
                        "feature_evidence": [
                            "Blue canvas exterior with padded shoulder straps"
                        ]
                    }
                ),
                "live": None,
                "match": None,
            },
            deep=True,
        )
        draft = AnswerOutput(
            answer_text=(
                "Widget Alpha is waterproof. Catalog evidence notes: Blue canvas "
                "exterior with padded shoulder straps."
            ),
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[],
        )
        state = {
            "transcript": "Find a blue canvas widget with padded straps",
            "semantic_query": "widget",
            "plan": "Use grounded evidence.",
        }
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(state, [product])

        self.assertIsNone(result)

    async def test_one_call_rejects_invented_number_even_with_exact_reason(self) -> None:
        product = _product().model_copy(
            update={"live": None, "match": None},
            deep=True,
        )
        draft = AnswerOutput(
            answer_text="Widget Alpha costs $99.",
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[],
        )
        state = {
            "transcript": "Find a widget",
            "semantic_query": "widget",
            "plan": "Use grounded evidence.",
        }
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(state, [product])

        self.assertIsNone(result)

    async def test_one_call_accepts_grounded_current_price_paraphrase(self) -> None:
        product = _product().model_copy(
            update={
                "live": _product().live.model_copy(
                    update={"origin": "live_serper"}
                )
            },
            deep=True,
        )
        draft = AnswerOutput(
            answer_text="Widget Alpha currently costs $21.95 and is in stock.",
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[LIVE_URL],
        )
        state = {
            "transcript": "Find the current price of Widget Alpha",
            "semantic_query": "widget",
            "plan": "Use grounded catalog and live evidence.",
        }
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(state, [product])

        self.assertEqual(result, draft)

    async def test_one_call_rejects_current_claim_for_recorded_price(self) -> None:
        product = _product().model_copy(
            update={
                "live": _product().live.model_copy(
                    update={"origin": "recorded_fixture"}
                )
            },
            deep=True,
        )
        draft = AnswerOutput(
            answer_text="Widget Alpha currently costs $21.95 and is in stock.",
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[LIVE_URL],
        )
        state = {
            "transcript": "Find the price of Widget Alpha",
            "semantic_query": "widget",
            "plan": "Use grounded evidence.",
        }
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(state, [product])

        self.assertIsNone(result)

    async def test_answer_call_uses_minimal_reasoning_and_aligned_prompt(self) -> None:
        product = _product().model_copy(
            update={"live": None, "match": None},
            deep=True,
        )
        structured = AsyncMock()
        structured.ainvoke.return_value = AnswerOutput(
            answer_text="Widget Alpha has a 2020 catalog price of $10.00.",
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[],
        )
        llm = Mock()
        llm.with_structured_output.return_value = structured
        state = {
            "transcript": "Find a widget",
            "semantic_query": "widget",
            "plan": "Use grounded evidence.",
            "products": [product],
        }

        with patch.dict("os.environ", {}, clear=True), patch(
            "graph.answer.get_llm",
            return_value=llm,
        ) as get_llm_mock:
            await _answer_call(state, "grounded evidence", feedback=None)

        get_llm_mock.assert_called_once_with(reasoning_effort="minimal")
        human_prompt = structured.ainvoke.await_args.args[0][1][1]
        self.assertIn(
            "Preserve every grounded fact from this reason while varying the wording naturally",
            human_prompt,
        )
        system_prompt = structured.ainvoke.await_args.args[0][0][1]
        self.assertIn("Never repeat or paraphrase the user's request as a reason", system_prompt)

    async def test_one_call_natural_answer_rejects_invented_rating(self) -> None:
        draft = AnswerOutput(
            answer_text="Widget Alpha has a 4.9-star catalog rating.",
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[],
        )
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(
                {"transcript": "Compare the options", "plan": "Compare."},
                [_product()],
            )

        self.assertIsNone(result)

    async def test_one_call_rejects_a_grounded_but_noncanonical_later_product(self) -> None:
        top = _product().model_copy(
            update={"live": None, "match": None},
            deep=True,
        )
        later_private = top.private.model_copy(
            update={
                "sku": "widget-beta",
                "title": "Widget Beta",
                "doc_id": "AMZ-WIDGET02",
            }
        )
        later = top.model_copy(
            update={"private": later_private},
            deep=True,
        )
        draft = AnswerOutput(
            answer_text="Widget Beta is the strongest option.",
            cited_doc_ids=["AMZ-WIDGET02"],
            cited_urls=[],
        )
        state = {
            "transcript": "Find a widget",
            "semantic_query": "widget",
            "plan": "Use grounded evidence.",
        }
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(state, [top, later])

        self.assertIsNone(result)

    async def test_requested_size_is_not_treated_as_product_evidence(self) -> None:
        draft = AnswerOutput(
            answer_text="Widget Alpha comes in medium and large.",
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[],
        )
        state = {
            "transcript": "Medium or large?",
            "plan": "Compare grounded evidence.",
            "shopping_context": ShoppingContext(
                product_query="widget",
                sizes=["medium", "large"],
                resolved_query="widget medium large",
            ),
        }
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(state, [_product()])

        self.assertIsNone(result)

    def test_unconfirmed_size_uses_only_grounded_price_without_a_caveat(self) -> None:
        state = {
            "transcript": "Medium or large?",
            "semantic_query": "widget",
            "plan": "Compare grounded evidence.",
            "shopping_context": ShoppingContext(
                product_query="widget",
                sizes=["medium", "large"],
                resolved_query="widget medium large",
            ),
        }

        top = build_top_recommendation([_product()], state)
        draft = _degraded_answer([_product()], state)

        self.assertEqual(top.reason, "Its web price is $21.95.")
        self.assertIn("$21.95", draft.answer_text)
        self.assertNotIn("closest grounded candidate", draft.answer_text)
        self.assertNotIn("matches your", draft.answer_text.casefold())
        self.assertNotIn("medium", draft.answer_text)
        self.assertNotIn("large", draft.answer_text)
        self.assertNotIn("does not confirm", draft.answer_text)

    def test_unconfirmed_adult_bag_omits_raw_query_fallback_rationale(self) -> None:
        product = _product().model_copy(
            update={
                "private": _product().private.model_copy(
                    update={
                        "title": "Wildkin Kids Overnighter Duffel Bag for Boys and Girls",
                        "feature_evidence": [],
                    }
                ),
                "live": None,
                "match": None,
            },
            deep=True,
        )
        state = {
            "transcript": "Give bag adults",
            "semantic_query": "Give bag adults",
            "shopping_context": ShoppingContext(
                product_query="bag",
                sizes=["adult"],
                resolved_query="bag adult",
            ),
        }

        top = build_top_recommendation([product], state)
        draft = _degraded_answer([product], state)

        self.assertEqual(top.reason, "")
        self.assertNotIn("Give bag adults", draft.answer_text)
        self.assertNotIn("closest grounded candidate", draft.answer_text.casefold())
        self.assertNotIn("matches your", draft.answer_text.casefold())
        self.assertLessEqual(len(draft.answer_text.split()), 30)

    def test_reason_without_feature_fit_uses_grounded_price_not_query_echo(self) -> None:
        state = {
            "transcript": "widget",
            "semantic_query": "widget",
        }

        top = build_top_recommendation([_product()], state)
        draft = _degraded_answer([_product()], state)

        self.assertEqual(top.reason, "Its web price is $21.95.")
        self.assertNotIn("widget request", top.reason.casefold())
        self.assertNotIn("matches your", draft.answer_text.casefold())
        self.assertLessEqual(len(draft.answer_text.split()), 30)

    async def test_unconfirmed_size_caveat_is_rejected(self) -> None:
        draft = AnswerOutput(
            answer_text=(
                "My top choice is Widget Alpha. It is the highest-ranked "
                "grounded match, but its evidence does not confirm medium or large."
            ),
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[LIVE_URL],
        )
        state = {
            "transcript": "Medium or large?",
            "plan": "Compare grounded evidence.",
            "shopping_context": ShoppingContext(
                product_query="widget",
                sizes=["medium", "large"],
                resolved_query="widget medium large",
            ),
        }
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(state, [_product()])

        self.assertIsNone(result)

    async def test_paraphrased_unconfirmed_evidence_caveat_is_rejected(self) -> None:
        draft = AnswerOutput(
            answer_text=(
                "My top choice is Widget Alpha. It is the closest grounded "
                "candidate for your widget request. The evidence does not "
                "confirm your preferred sizing."
            ),
            cited_doc_ids=["AMZ-WIDGET01"],
            cited_urls=[LIVE_URL],
        )
        state = {
            "transcript": "Medium or large?",
            "semantic_query": "widget",
            "plan": "Compare grounded evidence.",
            "shopping_context": ShoppingContext(
                product_query="widget",
                sizes=["medium", "large"],
                resolved_query="widget medium large",
            ),
        }
        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch("graph.answer._answer_call", new=AsyncMock(return_value=draft)):
            result = await natural_answer_once(state, [_product()])

        self.assertIsNone(result)

    async def test_missing_live_url_triggers_retry_and_fixed_citation_is_returned(self) -> None:
        answer_call = AsyncMock(side_effect=[_draft(include_live_url=False), _draft(include_live_url=True)])
        critic_call = AsyncMock(
            side_effect=[
                CriticOutput(
                    grounded=True,
                    citations_complete=False,
                    ungrounded_claims=[],
                    missing_citations=[LIVE_URL],
                ),
                CriticOutput(
                    grounded=True,
                    citations_complete=True,
                    ungrounded_claims=[],
                    missing_citations=[],
                ),
            ]
        )

        with patch("graph.answer._answer_call", answer_call), patch(
            "graph.answer._critic_call", critic_call
        ):
            result = await answerer_node(
                {
                    "products": [_product()],
                    "transcript": "What is its live price?",
                    "plan": "Use private and live evidence.",
                    "use_private": True,
                }
            )

        self.assertEqual(answer_call.await_count, 2)
        self.assertIn(LIVE_URL, [citation.url for citation in result["citations"]])
        self.assertIn("critic rejected first draft", result["steps"][0].detail)

    async def test_repeated_missing_live_url_degrades_to_deterministically_cited_answer(self) -> None:
        answer_call = AsyncMock(side_effect=[_draft(include_live_url=False), _draft(include_live_url=False)])
        incomplete = CriticOutput(
            grounded=True,
            citations_complete=False,
            ungrounded_claims=[],
            missing_citations=[LIVE_URL],
        )
        critic_call = AsyncMock(side_effect=[incomplete, incomplete])

        with patch("graph.answer._answer_call", answer_call), patch(
            "graph.answer._critic_call", critic_call
        ):
            result = await answerer_node(
                {
                    "products": [_product()],
                    "transcript": "What is its live price?",
                    "plan": "Use private and live evidence.",
                    "use_private": True,
                }
            )

        citations = {(citation.kind, citation.url or citation.label) for citation in result["citations"]}
        self.assertIn(("private", "AMZ-WIDGET01"), citations)
        self.assertIn(("live", LIVE_URL), citations)
        self.assertIn("degraded to evidence-only answer", result["steps"][0].detail)

    def test_critic_grounded_false_without_details_still_triggers_retry(self) -> None:
        critic = CriticOutput(
            grounded=False,
            citations_complete=True,
            ungrounded_claims=[],
            missing_citations=[],
        )

        self.assertEqual(
            _critic_issues(critic),
            ["The answer contains an ungrounded claim."],
        )


if __name__ == "__main__":
    unittest.main()
