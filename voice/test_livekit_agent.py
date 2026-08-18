"""Tests for grounded follow-up speech in the LiveKit pipeline."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, PropertyMock, patch

from livekit.agents.llm import ChatContext, ChatMessage

from contracts import (
    AssistantResult,
    Citation,
    ComparisonProduct,
    Conflict,
    MatchInfo,
    RagResult,
    ShoppingContext,
    StepEvent,
    WebResult,
)
from graph.fast_reply import FastReply, semantic_query
from graph.preferences import resolve_preferences
from voice.livekit_agent import (
    PROGRESS_CUE,
    ProductDiscoveryAgent,
    _quick_web_result,
    compose_live_followup,
)


def _private() -> RagResult:
    return RagResult(
        sku="nerf",
        title="Nerf Strongarm",
        price=13.99,
        rating=None,
        brand="Nerf",
        ingredients=None,
        doc_id="AMZ-NERF",
        image_url="https://example.com/image.jpg",
        product_url="https://example.com/product",
        category="Toys & Games",
        price_low=13.99,
        price_high=13.99,
        similarity=1.0,
        budget_fit="unknown",
    )


def _result(product: ComparisonProduct, *steps: StepEvent) -> AssistantResult:
    return AssistantResult(
        transcript="current Nerf price",
        plan="compare",
        answer_text="unused",
        products=[product],
        steps=list(steps),
        citations=[],
    )


class LiveFollowupTests(unittest.TestCase):
    def test_live_price_followup_preserves_provenance(self) -> None:
        live = WebResult(
            title="Nerf Strongarm",
            url="https://example.com/live",
            snippet="evidence",
            price=21.95,
            availability=None,
            rating=None,
            origin="live_serper",
        )
        product = ComparisonProduct(
            private=_private(),
            live=live,
            conflicts=[
                Conflict(
                    field="price",
                    private_value=13.99,
                    live_value=21.95,
                    note="different prices",
                )
            ],
            match=MatchInfo(similarity=1.0, verdict="same", reason="exact"),
        )
        text = compose_live_followup(_result(product))
        self.assertIn("current matched listing", text)
        self.assertIn("$21.95", text)
        self.assertIn("$13.99", text)

    def test_recorded_result_is_not_called_current(self) -> None:
        live = WebResult(
            title="Nerf Strongarm",
            url="https://example.com/recorded",
            snippet="evidence",
            price=21.95,
            availability=None,
            rating=None,
            origin="recorded_fixture",
        )
        product = ComparisonProduct(
            private=_private(),
            live=live,
            conflicts=[],
            match=MatchInfo(similarity=1.0, verdict="same", reason="exact"),
        )
        text = compose_live_followup(_result(product))
        self.assertIn("recorded web result", text)
        self.assertNotIn("current matched", text)

    def test_completed_search_without_match_is_honest(self) -> None:
        product = ComparisonProduct(
            private=_private(), live=None, conflicts=[], match=None
        )
        step = StepEvent(
            node="retriever",
            tool="web.search",
            started_at="2026-08-14T00:00:00Z",
            duration_ms=10,
            status="completed",
            detail="0 results",
        )
        text = compose_live_followup(_result(product, step))
        self.assertIn("couldn’t confirm an exact online match", text)


class _Speech:
    async def wait_for_playout(self) -> None:
        return None


class _Session:
    def __init__(self, timeline: list[tuple[str, str]] | None = None) -> None:
        self.spoken: list[str] = []
        self.calls: list[tuple[str, dict]] = []
        self.timeline = timeline
        self.state_listeners: list = []

    def on(self, event: str, callback) -> None:
        if event == "agent_state_changed":
            self.state_listeners.append(callback)

    def off(self, event: str, callback) -> None:
        if event == "agent_state_changed" and callback in self.state_listeners:
            self.state_listeners.remove(callback)

    def say(self, text: str, **kwargs) -> _Speech:
        self.spoken.append(text)
        self.calls.append((text, kwargs))
        if self.timeline is not None:
            self.timeline.append(("speech", text))
        state_event = type("StateEvent", (), {"new_state": "speaking"})()
        for callback in tuple(self.state_listeners):
            callback(state_event)
        if self.timeline is not None:
            self.timeline.append(("audio", text))
        return _Speech()


class _DelayedSession(_Session):
    def __init__(
        self,
        timeline: list[tuple[str, str]],
        *,
        first_frame_delay: float = 0.02,
    ) -> None:
        super().__init__(timeline)
        self.first_frame_delay = first_frame_delay

    def say(self, text: str, **kwargs) -> _Speech:
        self.spoken.append(text)
        self.calls.append((text, kwargs))
        self.timeline.append(("speech", text))

        def emit_first_frame() -> None:
            state_event = type("StateEvent", (), {"new_state": "speaking"})()
            for callback in tuple(self.state_listeners):
                callback(state_event)
            self.timeline.append(("audio", text))

        asyncio.get_running_loop().call_later(
            self.first_frame_delay,
            emit_first_frame,
        )
        return _Speech()


class CanonicalVoiceResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_preliminary_web_result_caps_at_six_with_one_twelve_candidate_call(self) -> None:
        class QuickTools:
            def __init__(self) -> None:
                self.calls: list[tuple[str, int]] = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return None

            async def web_search(self, query: str, num: int = 6):
                self.calls.append((query, num))
                return [
                    WebResult(
                        title=f"Grounded Web Product {index}",
                        url=f"https://example.com/web-{index}",
                        snippet="Grounded web listing",
                        price=float(10 + index),
                        origin="live_serper",
                    )
                    for index in range(12)
                ]

        tools = QuickTools()
        fast = FastReply(
            text="Catalog preview",
            product=_private(),
            citations=(Citation(kind="private", label="AMZ-NERF", url=None),),
            elapsed_ms=25,
            live_followup_needed=True,
        )

        with patch("voice.livekit_agent.MCPTools", return_value=tools):
            result = await _quick_web_result("Find current Nerf options", fast)

        self.assertEqual(len(tools.calls), 1)
        self.assertEqual(tools.calls[0][1], 12)
        self.assertEqual(len(result.products), 6)
        self.assertEqual(
            [product.live.url for product in result.products[:5]],
            [f"https://example.com/web-{index}" for index in range(5)],
        )
        self.assertEqual(result.products[5].private.doc_id, "AMZ-NERF")

    async def test_voice_followup_keeps_both_budget_range_bounds(self) -> None:
        fast = FastReply(
            text="What should I adjust?",
            product=None,
            citations=(),
            elapsed_ms=25,
            live_followup_needed=False,
            turn_kind="refinement",
            shopping_context=ShoppingContext(
                product_query="lego toy",
                resolved_query="lego toy",
            ),
        )
        completed = AssistantResult(
            transcript="I don't like them",
            plan="Preference refinement.",
            answer_text="What should I adjust?",
            products=[],
            steps=[],
            citations=[],
            shopping_context=fast.shopping_context,
        )
        fast_call = AsyncMock(return_value=fast)
        graph_call = AsyncMock(return_value=completed)
        agent = ProductDiscoveryAgent()
        agent._active_budget_min = 50.0
        agent._active_budget_max = 100.0
        agent._shopping_context = fast.shopping_context

        with (
            patch("voice.livekit_agent.build_fast_reply", new=fast_call),
            patch("voice.livekit_agent.run_full_graph", new=graph_call),
            patch.object(
                ProductDiscoveryAgent,
                "session",
                new_callable=PropertyMock,
                return_value=_Session(),
            ),
        ):
            await agent.on_user_turn_completed(
                ChatContext(),
                ChatMessage(role="user", content=["I don't like them"]),
            )
            await asyncio.gather(*tuple(agent._tasks))

        self.assertEqual(
            fast_call.await_args.args[0],
            "I don't like them between $50 and $100",
        )
        graph_context = graph_call.await_args.kwargs["dialogue_context"]
        self.assertEqual(graph_context["budget_min"], 50.0)
        self.assertEqual(graph_context["budget_max"], 100.0)

    async def test_preliminary_web_result_puts_its_recommendation_first(self) -> None:
        class QuickTools:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return None

            async def web_search(self, _query: str, num: int = 6):
                del num
                return [
                    WebResult(
                        title="Below Range LEGO Toy",
                        url="https://example.com/low",
                        snippet="Grounded web listing",
                        price=40.0,
                        origin="live_serper",
                    ),
                    WebResult(
                        title="In Range LEGO Toy",
                        url="https://example.com/in-range",
                        snippet="Grounded web listing",
                        price=75.0,
                        origin="live_serper",
                    ),
                    WebResult(
                        title="Above Range LEGO Toy",
                        url="https://example.com/high",
                        snippet="Grounded web listing",
                        price=110.0,
                        origin="live_serper",
                    ),
                ]

        fast = FastReply(
            text="Catalog preview",
            product=_private(),
            citations=(Citation(kind="private", label="AMZ-NERF", url=None),),
            elapsed_ms=25,
            live_followup_needed=True,
        )
        with patch("voice.livekit_agent.MCPTools", return_value=QuickTools()):
            result = await _quick_web_result(
                "lego toy between $50 and $100",
                fast,
            )

        self.assertEqual(result.products[0].live.url, "https://example.com/in-range")
        self.assertEqual(
            result.top_recommendation.product_key,
            "live:https://example.com/in-range",
        )
        self.assertIn(result.top_recommendation.reason, result.answer_text)
        self.assertLessEqual(len(result.answer_text.split()), 30)

    async def test_clarification_is_resolved_by_the_full_conversation_graph(self) -> None:
        fast = FastReply(
            text="Which feature matters?",
            product=None,
            citations=(),
            elapsed_ms=25,
            live_followup_needed=False,
            turn_kind="clarification",
            shopping_context=ShoppingContext(
                product_query="groceries",
                resolved_query="groceries",
                is_followup=True,
            ),
        )
        completed = AssistantResult(
            transcript="Yeah",
            plan="Conversation-aware clarification.",
            answer_text="Would you like pantry staples or fresh ingredients?",
            products=[],
            steps=[],
            citations=[],
            shopping_context=fast.shopping_context,
        )
        graph_call = AsyncMock(return_value=completed)
        session = _Session()
        agent = ProductDiscoveryAgent()
        agent._shopping_context = ShoppingContext(
            product_query="groceries",
            resolved_query="groceries",
        )
        agent._last_answer_text = "Would you like pantry staples or fresh food?"

        with (
            patch(
                "voice.livekit_agent.build_fast_reply",
                new=AsyncMock(return_value=fast),
            ),
            patch("voice.livekit_agent.run_full_graph", new=graph_call),
            patch.object(
                ProductDiscoveryAgent,
                "session",
                new_callable=PropertyMock,
                return_value=session,
            ),
        ):
            await agent.on_user_turn_completed(
                ChatContext(),
                ChatMessage(role="user", content=["Yeah"]),
            )
            await asyncio.gather(*tuple(agent._tasks))

        graph_call.assert_awaited_once()
        self.assertEqual(graph_call.await_args.args[0], "Yeah")
        self.assertEqual(
            graph_call.await_args.kwargs["dialogue_context"]["previous_answer"],
            "Would you like pantry staples or fresh food?",
        )
        self.assertEqual(session.spoken, [PROGRESS_CUE, completed.answer_text])

    async def test_live_routing_is_metadata_not_fake_shopper_text(self) -> None:
        fast = FastReply(
            text="I’m checking the matches.",
            product=None,
            citations=(),
            elapsed_ms=25,
            live_followup_needed=True,
            turn_kind="web_fallback",
            shopping_context=ShoppingContext(
                product_query="travel bag",
                resolved_query="travel bag",
            ),
        )
        completed = AssistantResult(
            transcript="Find a travel bag",
            plan="Search catalog and live evidence.",
            answer_text="Here are the strongest grounded travel bags.",
            products=[],
            steps=[],
            citations=[],
            shopping_context=fast.shopping_context,
        )
        graph_call = AsyncMock(return_value=completed)
        session = _Session()
        agent = ProductDiscoveryAgent()

        with (
            patch(
                "voice.livekit_agent.build_fast_reply",
                new=AsyncMock(return_value=fast),
            ),
            patch("voice.livekit_agent.run_full_graph", new=graph_call),
            patch.object(
                ProductDiscoveryAgent,
                "session",
                new_callable=PropertyMock,
                return_value=session,
            ),
        ):
            await agent.on_user_turn_completed(
                ChatContext(),
                ChatMessage(role="user", content=["Find a travel bag"]),
            )
            await asyncio.gather(*tuple(agent._tasks))

        self.assertEqual(graph_call.await_args.args[0], "Find a travel bag")
        self.assertTrue(graph_call.await_args.kwargs["dialogue_context"]["force_live"])

    async def test_named_product_drops_stale_product_context_and_budget(self) -> None:
        prior = ShoppingContext(
            product_query="mens sportswear",
            sizes=["medium"],
            resolved_query="mens sportswear medium",
        )
        updated = ShoppingContext(
            product_query="iPhone 12",
            resolved_query="iPhone 12",
        )
        fast = FastReply(
            text="I’m checking current iPhone 12 listings.",
            product=None,
            citations=(),
            elapsed_ms=25,
            live_followup_needed=True,
            turn_kind="web_fallback",
            shopping_context=updated,
        )
        completed = AssistantResult(
            transcript="iPhone 12",
            plan="Search current listings.",
            answer_text="Here are the grounded iPhone 12 listings I found.",
            products=[],
            steps=[],
            citations=[],
            shopping_context=updated,
        )
        fast_call = AsyncMock(return_value=fast)
        graph_call = AsyncMock(return_value=completed)
        session = _Session()
        agent = ProductDiscoveryAgent()
        agent._shopping_context = prior
        agent._active_budget_max = 20.0

        with (
            patch("voice.livekit_agent.build_fast_reply", new=fast_call),
            patch("voice.livekit_agent.run_full_graph", new=graph_call),
            patch.object(
                ProductDiscoveryAgent,
                "session",
                new_callable=PropertyMock,
                return_value=session,
            ),
        ):
            await agent.on_user_turn_completed(
                ChatContext(),
                ChatMessage(role="user", content=["iPhone 12"]),
            )
            await asyncio.gather(*tuple(agent._tasks))

        self.assertEqual(fast_call.await_args.args[0], "iPhone 12")
        self.assertEqual(fast_call.await_args.kwargs["dialogue_context"], {})
        self.assertEqual(
            graph_call.await_args.kwargs["dialogue_context"],
            {"force_live": True},
        )

    async def test_full_graph_receives_pre_turn_preferences(self) -> None:
        prior = ShoppingContext(product_query="product", resolved_query="product")
        updated = ShoppingContext(
            product_query="home",
            resolved_query="home",
            preference_changed=True,
            is_followup=True,
        )
        fast = FastReply(
            text="I found a grounded home option.",
            product=None,
            citations=(),
            elapsed_ms=25,
            live_followup_needed=False,
            turn_kind="preference_update",
            shopping_context=updated,
        )
        completed = AssistantResult(
            transcript="I need something for home",
            plan="Search Home & Kitchen.",
            answer_text="A home organizer is the strongest grounded match.",
            products=[],
            steps=[],
            citations=[],
            shopping_context=updated,
        )
        graph_call = AsyncMock(return_value=completed)
        session = _Session()
        agent = ProductDiscoveryAgent()
        agent._shopping_context = prior
        agent._active_budget_max = 10.0

        with (
            patch(
                "voice.livekit_agent.build_fast_reply",
                new=AsyncMock(return_value=fast),
            ),
            patch("voice.livekit_agent.run_full_graph", new=graph_call),
            patch.object(
                ProductDiscoveryAgent,
                "session",
                new_callable=PropertyMock,
                return_value=session,
            ),
        ):
            await agent.on_user_turn_completed(
                ChatContext(),
                ChatMessage(role="user", content=["I need something for home"]),
            )
            await asyncio.gather(*tuple(agent._tasks))

        graph_context = graph_call.await_args.kwargs["dialogue_context"]
        self.assertEqual(graph_context["shopping_context"], prior)
        self.assertNotEqual(graph_context["shopping_context"], updated)

    async def test_negative_color_followup_uses_persisted_backpack_context(self) -> None:
        prior = ShoppingContext(
            product_query="backpack",
            resolved_query="backpack",
        )
        transcript = "I don't want black"
        updated = await resolve_preferences(
            transcript,
            semantic_query(transcript),
            prior,
            allow_llm=False,
        )
        fast = FastReply(
            text="I found a grounded nonblack backpack.",
            product=None,
            citations=(),
            elapsed_ms=25,
            live_followup_needed=False,
            turn_kind="preference_update",
            resolved_transcript="Find backpack",
            shopping_context=updated,
        )
        completed = AssistantResult(
            transcript=transcript,
            plan="Search backpacks with grounded exclusions.",
            answer_text="The strongest grounded backpack avoids black.",
            products=[],
            steps=[],
            citations=[],
            shopping_context=updated,
        )
        fast_call = AsyncMock(return_value=fast)
        graph_call = AsyncMock(return_value=completed)
        agent = ProductDiscoveryAgent()
        agent._shopping_context = prior

        with (
            patch("voice.livekit_agent.build_fast_reply", new=fast_call),
            patch("voice.livekit_agent.run_full_graph", new=graph_call),
            patch.object(
                ProductDiscoveryAgent,
                "session",
                new_callable=PropertyMock,
                return_value=_Session(),
            ),
        ):
            await agent.on_user_turn_completed(
                ChatContext(),
                ChatMessage(role="user", content=[transcript]),
            )
            await asyncio.gather(*tuple(agent._tasks))

        self.assertEqual(updated.product_query, "backpack")
        self.assertEqual(updated.resolved_query, "backpack")
        self.assertEqual(updated.excluded, ["black"])
        self.assertNotIn("don't want", updated.resolved_query)
        self.assertEqual(
            fast_call.await_args.kwargs["dialogue_context"]["shopping_context"],
            prior,
        )
        self.assertEqual(graph_call.await_args.args[0], "Find backpack")
        self.assertNotIn("don't want", graph_call.await_args.args[0])
        self.assertEqual(
            graph_call.await_args.kwargs["dialogue_context"]["shopping_context"],
            prior,
        )
        self.assertEqual(agent._shopping_context, updated)

    async def test_transient_progress_cue_precedes_one_aligned_final_answer(self) -> None:
        events: list[tuple[str, dict]] = []
        timeline: list[tuple[str, str]] = []

        async def capture(event_type: str, data: dict) -> None:
            events.append((event_type, data))
            timeline.append(("event", event_type))

        fast = FastReply(
            text="I found a quick catalog option.",
            product=None,
            citations=(),
            elapsed_ms=25,
            live_followup_needed=False,
            turn_kind="catalog",
        )
        completed = AssistantResult(
            transcript="Find blue storage",
            plan="Compare grounded matches.",
            answer_text=(
                "The blue storage bin is the strongest match because its fabric "
                "exterior confirms your color preference, and the alternatives "
                "are available on screen with detailed price, source, size, "
                "material, and availability evidence ready for your review."
            ),
            products=[],
            steps=[],
            citations=[],
        )
        session = _Session(timeline)
        agent = ProductDiscoveryAgent(event_sink=capture)

        with (
            patch(
                "voice.livekit_agent.build_fast_reply",
                new=AsyncMock(return_value=fast),
            ),
            patch(
                "voice.livekit_agent.run_full_graph",
                new=AsyncMock(return_value=completed),
            ),
            patch.object(
                ProductDiscoveryAgent,
                "session",
                new_callable=PropertyMock,
                return_value=session,
            ),
        ):
            await agent.on_user_turn_completed(
                ChatContext(),
                ChatMessage(role="user", content=["Find blue storage"]),
            )
            await asyncio.gather(*tuple(agent._tasks))

        result_events = [data for kind, data in events if kind == "assistant_result"]
        started_events = [data for kind, data in events if kind == "turn_started"]
        self.assertEqual(len(started_events), 1)
        self.assertEqual(started_events[0]["answer_text"], PROGRESS_CUE)
        self.assertTrue(started_events[0]["transient"])
        self.assertEqual(len(result_events), 1)
        self.assertEqual(session.spoken, [PROGRESS_CUE, result_events[0]["answer_text"]])
        self.assertEqual(session.calls[0][1], {"add_to_chat_ctx": False})
        self.assertNotEqual(session.spoken[-1], fast.text)
        self.assertLessEqual(len(session.spoken[-1].split()), 30)
        self.assertLess(
            timeline.index(("audio", PROGRESS_CUE)),
            timeline.index(("event", "turn_started")),
        )
        self.assertLess(
            timeline.index(("audio", result_events[0]["answer_text"])),
            timeline.index(("event", "assistant_result")),
        )

    async def test_fast_work_overlaps_progress_cue_first_frame_startup(self) -> None:
        events: list[tuple[str, dict]] = []
        timeline: list[tuple[str, str]] = []

        async def capture(event_type: str, data: dict) -> None:
            events.append((event_type, data))
            timeline.append(("event", event_type))

        fast = FastReply(
            text="I found a grounded catalog preview.",
            product=None,
            citations=(),
            elapsed_ms=25,
            live_followup_needed=False,
            turn_kind="catalog",
        )
        completed = AssistantResult(
            transcript="Find a Barbie doll",
            plan="Compare grounded matches.",
            answer_text="Barbie Fashionistas is the strongest grounded match.",
            products=[],
            steps=[],
            citations=[],
        )

        async def build_fast(*_args, **_kwargs) -> FastReply:
            timeline.append(("work", "fast_reply"))
            return fast

        session = _DelayedSession(timeline)
        agent = ProductDiscoveryAgent(event_sink=capture)
        with (
            patch("voice.livekit_agent.build_fast_reply", new=build_fast),
            patch(
                "voice.livekit_agent.run_full_graph",
                new=AsyncMock(return_value=completed),
            ),
            patch.object(
                ProductDiscoveryAgent,
                "session",
                new_callable=PropertyMock,
                return_value=session,
            ),
        ):
            await agent.on_user_turn_completed(
                ChatContext(),
                ChatMessage(role="user", content=["Find a Barbie doll"]),
            )
            await asyncio.gather(*tuple(agent._tasks))

        result_events = [data for kind, data in events if kind == "assistant_result"]
        self.assertLess(
            timeline.index(("work", "fast_reply")),
            timeline.index(("audio", PROGRESS_CUE)),
        )
        self.assertLess(
            timeline.index(("audio", PROGRESS_CUE)),
            timeline.index(("event", "turn_started")),
        )
        self.assertEqual(len(result_events), 1)
        self.assertEqual(
            session.spoken,
            [PROGRESS_CUE, result_events[0]["answer_text"]],
        )
        self.assertLess(
            timeline.index(("audio", result_events[0]["answer_text"])),
            timeline.index(("event", "assistant_result")),
        )


if __name__ == "__main__":
    unittest.main()
