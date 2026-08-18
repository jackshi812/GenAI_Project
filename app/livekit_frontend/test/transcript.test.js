import test from "node:test";
import assert from "node:assert/strict";

import {
  canonicalTranscriptForProductEvent,
  isShopperTranscription,
  mergeTranscriptChunk,
  shouldRenderTranscription,
} from "../src/transcript.js";

test("accepts a transcript sent directly as the shopper", () => {
  assert.equal(
    isShopperTranscription({
      participantIdentity: "shopper-1",
      localIdentity: "shopper-1",
    }),
    true,
  );
});

test("accepts an agent-forwarded transcript for the shopper microphone", () => {
  assert.equal(
    isShopperTranscription({
      attributes: { "lk.transcribed_track_id": "TR_user" },
      participantIdentity: "agent-1",
      localIdentity: "shopper-1",
      localMicrophoneTrackId: "TR_user",
    }),
    true,
  );
});

test("rejects the assistant transcript", () => {
  assert.equal(
    isShopperTranscription({
      attributes: { "lk.transcribed_track_id": "TR_agent" },
      participantIdentity: "agent-1",
      localIdentity: "shopper-1",
      localMicrophoneTrackId: "TR_user",
    }),
    false,
  );
});

test("combines delta chunks and tolerates cumulative chunks", () => {
  assert.equal(mergeTranscriptChunk("Find me", " a puzzle"), "Find me a puzzle");
  assert.equal(mergeTranscriptChunk("Find me", "Find me a puzzle"), "Find me a puzzle");
  assert.equal(mergeTranscriptChunk("Find me", "me"), "Find me");
});

test("a product event can commit the canonical user transcript before its reply", () => {
  assert.equal(
    canonicalTranscriptForProductEvent("  Find a blue travel bag  "),
    "Find a blue travel bag",
  );
});

test("late transcript chunks cannot create text after a turn was committed", () => {
  assert.equal(shouldRenderTranscription({ turnCommitted: true }), false);
  assert.equal(shouldRenderTranscription({ turnCommitted: false }), true);
});
