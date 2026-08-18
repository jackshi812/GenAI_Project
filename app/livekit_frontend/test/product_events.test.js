import test from "node:test";
import assert from "node:assert/strict";

import {
  externalTurnCommittedEvent,
  PENDING_ASSISTANT_MESSAGE,
  productEventPolicy,
  shouldApplyExternalTurn,
} from "../src/product_events.js";

test("pending copy sounds like a helpful shopping assistant", () => {
  assert.equal(
    PENDING_ASSISTANT_MESSAGE,
    "Give me a moment while I pull up the best matches.",
  );
});

test("fast evidence remains a preview rather than a second chat response", () => {
  assert.deepEqual(productEventPolicy("fast_reply"), {
    showAssistantMessage: false,
    showThinkingMessage: true,
    readyForNewTurn: false,
  });
});

test("a stale completed turn cannot replace a newer thinking row", () => {
  assert.equal(
    shouldApplyExternalTurn({
      requestId: "old-turn",
      pendingRequestId: "new-turn",
      signature: "old-turn:old answer",
    }),
    false,
  );
  assert.equal(
    shouldApplyExternalTurn({
      requestId: "new-turn",
      pendingRequestId: "new-turn",
      signature: "new-turn:new answer",
    }),
    true,
  );
});

test("the completed result becomes the one committed assistant response", () => {
  assert.deepEqual(productEventPolicy("assistant_result"), {
    showAssistantMessage: true,
    showThinkingMessage: false,
    readyForNewTurn: true,
  });
});

test("the component acknowledges only after it has committed the typed turn", () => {
  assert.deepEqual(externalTurnCommittedEvent("typed-123"), {
    type: "turn_committed",
    event_id: "committed-typed-123",
    data: { request_id: "typed-123" },
  });
});
