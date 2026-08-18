export const TRANSCRIBED_TRACK_ATTRIBUTE = "lk.transcribed_track_id";

export function isShopperTranscription({
  attributes = {},
  participantIdentity = "",
  localIdentity = "",
  localMicrophoneTrackId = "",
}) {
  if (!localIdentity) return false;
  if (participantIdentity === localIdentity) return true;

  const transcribedTrackId = attributes[TRANSCRIBED_TRACK_ATTRIBUTE] || "";
  return Boolean(
    transcribedTrackId
      && localMicrophoneTrackId
      && transcribedTrackId === localMicrophoneTrackId,
  );
}

export function mergeTranscriptChunk(current, incoming) {
  const accumulated = String(current || "");
  const chunk = String(incoming || "");
  if (!chunk) return accumulated;
  if (!accumulated) return chunk;

  // LiveKit currently yields deltas, while older clients may yield the full
  // accumulated value. Supporting both avoids duplicated words after an SDK
  // upgrade or when Cloud and browser client versions briefly differ.
  if (chunk.startsWith(accumulated)) return chunk;
  if (accumulated.endsWith(chunk)) return accumulated;
  return `${accumulated}${chunk}`;
}

export function canonicalTranscriptForProductEvent(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

export function shouldRenderTranscription({ turnCommitted = false } = {}) {
  return !turnCommitted;
}
