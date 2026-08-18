export const DEFAULT_TYPED_AUDIO_SYNC_TIMEOUT_MS = 1250;

function defaultContextFactory() {
  const AudioContextClass = globalThis.AudioContext || globalThis.webkitAudioContext;
  return AudioContextClass ? new AudioContextClass() : null;
}

function base64ArrayBuffer(encoded, decodeBase64) {
  const binary = decodeBase64(String(encoded || ""));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

function stopSource(source) {
  if (!source) return;
  try {
    source.stop();
  } catch (_error) {
    // A source that already ended is harmless.
  }
}

export function createTypedTurnEpoch({ stopAudio = () => {} } = {}) {
  let epoch = 0;
  let pendingRequestId = null;

  function invalidate() {
    epoch += 1;
    pendingRequestId = null;
    try {
      stopAudio();
    } catch (_error) {
      // Lifecycle invalidation must still win if audio cleanup is unavailable.
    }
    return epoch;
  }

  function begin(requestId) {
    const nextEpoch = invalidate();
    const normalized = String(requestId || "").trim();
    pendingRequestId = normalized || null;
    return nextEpoch;
  }

  function isCurrent(requestId, expectedEpoch) {
    return Boolean(
      pendingRequestId
      && String(requestId || "").trim() === pendingRequestId
      && expectedEpoch === epoch
    );
  }

  function capture(requestId) {
    return isCurrent(requestId, epoch) ? epoch : null;
  }

  function complete(requestId, expectedEpoch) {
    if (!isCurrent(requestId, expectedEpoch)) return false;
    pendingRequestId = null;
    return true;
  }

  return {
    begin,
    capture,
    complete,
    invalidate,
    isCurrent,
    pendingRequestId: () => pendingRequestId,
  };
}

export function createTypedAudioController({
  contextFactory = defaultContextFactory,
  decodeBase64 = globalThis.atob?.bind(globalThis),
  setTimer = globalThis.setTimeout.bind(globalThis),
  clearTimer = globalThis.clearTimeout.bind(globalThis),
} = {}) {
  let context = null;
  let activeSource = null;
  let cancelPending = null;
  let generation = 0;

  async function arm() {
    try {
      if (!context) context = contextFactory();
      if (!context) return false;
      if (context.state === "suspended") await context.resume();
      return context.state === "running";
    } catch (_error) {
      return false;
    }
  }

  function play(encoded, { timeoutMs = DEFAULT_TYPED_AUDIO_SYNC_TIMEOUT_MS } = {}) {
    if (!encoded || !context || !decodeBase64) return Promise.resolve(false);
    const playGeneration = ++generation;
    const boundedTimeout = Number.isFinite(Number(timeoutMs))
      ? Math.max(0, Number(timeoutMs))
      : DEFAULT_TYPED_AUDIO_SYNC_TIMEOUT_MS;

    return new Promise((resolve) => {
      let source = null;
      let settled = false;
      let timeoutHandle = null;
      let clockHandle = null;

      const finish = (started) => {
        if (settled) return;
        settled = true;
        if (cancelPending === cancel) cancelPending = null;
        if (timeoutHandle !== null) clearTimer(timeoutHandle);
        if (clockHandle !== null) clearTimer(clockHandle);
        if (!started) {
          stopSource(source);
          if (activeSource === source) activeSource = null;
        }
        resolve(started);
      };
      const cancel = () => finish(false);
      cancelPending = cancel;

      timeoutHandle = setTimer(() => finish(false), boundedTimeout);
      void (async () => {
        try {
          if (context.state === "suspended") await context.resume();
          if (
            settled
            || playGeneration !== generation
            || context.state !== "running"
          ) {
            finish(false);
            return;
          }

          const audioBuffer = await context.decodeAudioData(
            base64ArrayBuffer(encoded, decodeBase64),
          );
          if (settled || playGeneration !== generation) return;

          stopSource(activeSource);
          source = context.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(context.destination);
          const scheduledStart = context.currentTime + 0.02;
          source.start(scheduledStart);
          activeSource = source;

          const observeAudioClock = () => {
            if (settled || playGeneration !== generation) return;
            if (
              context.state === "running"
              && context.currentTime >= scheduledStart
            ) {
              finish(true);
              return;
            }
            clockHandle = setTimer(observeAudioClock, 8);
          };
          observeAudioClock();
        } catch (_error) {
          finish(false);
        }
      })();
    });
  }

  function stop() {
    generation += 1;
    if (cancelPending) cancelPending();
    stopSource(activeSource);
    activeSource = null;
  }

  async function prepare() {
    stop();
    return arm();
  }

  return { arm, play, prepare, stop };
}

export async function synchronizeTypedTurn(
  turn,
  { playAudio, commit, isCurrent = () => true },
) {
  if (!isCurrent(turn)) return false;
  let audioStarted = false;
  if (turn?.audio_base64) {
    try {
      audioStarted = await playAudio(turn.audio_base64);
    } catch (_error) {
      audioStarted = false;
    }
  }
  if (!isCurrent(turn)) return false;
  commit(turn, audioStarted);
  return audioStarted;
}
