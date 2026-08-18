export const PENDING_ASSISTANT_MESSAGE =
  "Give me a moment while I pull up the best matches.";

export function productEventPolicy(eventType) {
  if (eventType === "turn_started") {
    return {
      showAssistantMessage: false,
      showThinkingMessage: true,
      readyForNewTurn: false,
    };
  }
  if (eventType === "fast_reply") {
    return {
      showAssistantMessage: false,
      showThinkingMessage: true,
      readyForNewTurn: false,
    };
  }
  if (eventType === "assistant_result") {
    return {
      showAssistantMessage: true,
      showThinkingMessage: false,
      readyForNewTurn: true,
    };
  }
  return null;
}

export function externalTurnCommittedEvent(requestId) {
  const normalized = String(requestId || "").trim();
  if (!normalized) return null;
  return {
    type: "turn_committed",
    event_id: `committed-${normalized}`,
    data: { request_id: normalized },
  };
}

export function shouldApplyExternalTurn({
  requestId,
  pendingRequestId = null,
  signature,
  lastSignature = null,
}) {
  if (!requestId || !signature || signature === lastSignature) return false;
  return !pendingRequestId || requestId === pendingRequestId;
}
