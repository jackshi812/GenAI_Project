import { Streamlit } from "streamlit-component-lib";
import {
  ConnectionState,
  Room,
  RoomEvent,
  Track,
} from "livekit-client";
import "./style.css";
import {
  canonicalTranscriptForProductEvent,
  isShopperTranscription,
  mergeTranscriptChunk,
  shouldRenderTranscription,
} from "./transcript.js";
import {
  externalTurnCommittedEvent,
  PENDING_ASSISTANT_MESSAGE,
  productEventPolicy,
  shouldApplyExternalTurn,
} from "./product_events.js";
import {
  createTypedAudioController,
  createTypedTurnEpoch,
  synchronizeTypedTurn,
} from "./typed_audio.js";

const elements = {
  audio: document.getElementById("agent-audio"),
  composer: document.getElementById("composer"),
  error: document.getElementById("error"),
  input: document.getElementById("typed-input"),
  messages: document.getElementById("messages"),
  restart: document.getElementById("restart"),
  send: document.getElementById("send"),
  start: document.getElementById("start"),
  stateDot: document.getElementById("state-dot"),
  status: document.getElementById("status"),
  stop: document.getElementById("stop"),
  timer: document.getElementById("timer"),
  visualizer: document.getElementById("visualizer"),
  voiceHint: document.getElementById("voice-hint"),
};

let config = null;
let room = null;
let connectedRoom = null;
let startedAt = null;
let timerHandle = null;
let lastResultId = null;
let lastFastId = null;
let lastExternalTurnId = null;
let readyForNewTurn = true;
let currentVoiceMessageId = null;
let currentAssistantMessageId = null;
let voiceTurnCommitted = false;
const userSegments = new Map();
const messageNodes = new Map();
const typedAudio = createTypedAudioController();
const typedTurns = createTypedTurnEpoch({
  stopAudio: () => typedAudio.stop(),
});

function uniqueId(prefix) {
  const suffix = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  return `${prefix}-${suffix}`;
}

function setStatus(text, state = "idle") {
  elements.status.textContent = text;
  elements.stateDot.dataset.state = state;
  elements.visualizer.dataset.state = state;
}

function showError(message) {
  elements.error.textContent = message;
  elements.error.classList.remove("hidden");
}

function clearError() {
  elements.error.textContent = "";
  elements.error.classList.add("hidden");
}

function scrollMessages() {
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function updateMessage(id, text, pending = false) {
  const node = messageNodes.get(id);
  if (!node) return null;
  const bubble = node.querySelector(".message-bubble");
  bubble.textContent = text;
  bubble.classList.toggle("pending", pending);
  scrollMessages();
  return node;
}

function appendMessage(role, text, id = uniqueId(role), pending = false) {
  if (messageNodes.has(id)) {
    updateMessage(id, text, pending);
    return id;
  }

  const row = document.createElement("article");
  row.className = `message-row ${role}`;
  row.dataset.messageId = id;

  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "You" : "Store assistant";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.classList.toggle("pending", pending);
  bubble.textContent = text;

  row.append(label, bubble);
  elements.messages.append(row);
  messageNodes.set(id, row);
  scrollMessages();
  return id;
}

function resetMessages() {
  elements.messages.replaceChildren();
  messageNodes.clear();
  appendMessage(
    "assistant",
    "Hi! Tell me what you’re shopping for. You can type below or start the microphone.",
    "welcome",
  );
  userSegments.clear();
  currentVoiceMessageId = null;
  currentAssistantMessageId = null;
  readyForNewTurn = true;
  voiceTurnCommitted = false;
  lastFastId = null;
  lastResultId = null;
  lastExternalTurnId = null;
}

function combinedTranscript() {
  return [...userSegments.values()]
    .map((segment) => segment.text)
    .filter(Boolean)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

function beginVoiceTurn() {
  typedTurns.invalidate();
  userSegments.clear();
  currentVoiceMessageId = uniqueId("voice-user");
  currentAssistantMessageId = null;
  lastFastId = null;
  lastResultId = null;
  readyForNewTurn = false;
  voiceTurnCommitted = false;
  appendMessage("user", "Listening…", currentVoiceMessageId, true);
}

function commitVoiceTranscript(value) {
  const transcript = canonicalTranscriptForProductEvent(value);
  if (!transcript) return;
  if (!currentVoiceMessageId || readyForNewTurn) beginVoiceTurn();
  userSegments.clear();
  userSegments.set("canonical", { text: transcript, final: true });
  updateMessage(currentVoiceMessageId, transcript, false);
  voiceTurnCommitted = true;
}

function renderVoiceTranscript() {
  if (!currentVoiceMessageId) beginVoiceTurn();
  const text = combinedTranscript();
  updateMessage(currentVoiceMessageId, text || "Listening…", !text);
}

function updateTimer() {
  if (!startedAt) return;
  const seconds = Math.floor((Date.now() - startedAt) / 1000);
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainder = (seconds % 60).toString().padStart(2, "0");
  elements.timer.textContent = `${minutes}:${remainder}`;
}

function beginTimer() {
  startedAt = Date.now();
  updateTimer();
  clearInterval(timerHandle);
  timerHandle = setInterval(updateTimer, 250);
}

function endTimer() {
  clearInterval(timerHandle);
  timerHandle = null;
  startedAt = null;
  elements.timer.textContent = "00:00";
}

async function handleTranscription(reader, participantInfo) {
  try {
    const attributes = reader.info?.attributes || {};
    const segmentId = attributes["lk.segment_id"] || uniqueId("segment");
    const localParticipant = room?.localParticipant;
    const microphone = localParticipant?.getTrackPublication(Track.Source.Microphone);
    const isUser = isShopperTranscription({
      attributes,
      participantIdentity: participantInfo?.identity,
      localIdentity: localParticipant?.identity,
      localMicrophoneTrackId: microphone?.trackSid,
    });
    if (!isUser) return;

    if (
      shouldRenderTranscription({ turnCommitted: voiceTurnCommitted })
      && (readyForNewTurn || !currentVoiceMessageId)
    ) beginVoiceTurn();
    let message = "";
    if (reader[Symbol.asyncIterator]) {
      for await (const chunk of reader) {
        message = mergeTranscriptChunk(message, chunk);
        if (shouldRenderTranscription({ turnCommitted: voiceTurnCommitted })) {
          userSegments.set(segmentId, { text: message.trim(), final: false });
          renderVoiceTranscript();
          setStatus("Listening…", "listening");
        }
      }
    } else {
      message = await reader.readAll();
    }

    // LiveKit adds the final marker on the stream trailer. Read it after the
    // stream closes; the header is intentionally marked as interim.
    const finalAttributes = reader.info?.attributes || {};
    const isFinal = finalAttributes["lk.transcription_final"] === "true";
    if (!shouldRenderTranscription({ turnCommitted: voiceTurnCommitted })) return;
    userSegments.set(segmentId, { text: message.trim(), final: isFinal });
    renderVoiceTranscript();
    if (isFinal) {
      assistantMessageForVoice(PENDING_ASSISTANT_MESSAGE, true);
      setStatus("Finding a grounded match…", "thinking");
      elements.voiceHint.textContent = "Your message was sent automatically.";
    }
  } catch (_error) {
    showError("Live transcription was interrupted. Keep speaking or restart the microphone.");
    setStatus("Listening…", "listening");
  }
}

function assistantMessageForVoice(text, pending = false) {
  if (!currentAssistantMessageId) {
    currentAssistantMessageId = uniqueId("voice-assistant");
    appendMessage("assistant", text, currentAssistantMessageId, pending);
  } else {
    updateMessage(currentAssistantMessageId, text, pending);
  }
}

function emitEnvelope(envelope, fallbackId) {
  const eventId = envelope.event_id || fallbackId;
  Streamlit.setComponentValue({ ...envelope, event_id: eventId });
}

function handleProductEvent(payload, _participant, _kind, topic) {
  if (topic !== "product.discovery") return;
  try {
    const envelope = JSON.parse(new TextDecoder().decode(payload));
    const policy = productEventPolicy(envelope.type);
    if (!policy) return;
    let resultId = null;
    if (envelope.type === "assistant_result") {
      resultId = `result:${envelope.data.transcript}:${envelope.data.answer_text}`;
      if (resultId === lastResultId) return;
      lastResultId = resultId;
    }
    commitVoiceTranscript(envelope.data?.transcript);
    if (envelope.type === "turn_started") {
      readyForNewTurn = policy.readyForNewTurn;
      if (policy.showThinkingMessage) {
        assistantMessageForVoice(
          envelope.data?.answer_text || PENDING_ASSISTANT_MESSAGE,
          true,
        );
      }
      emitEnvelope(
        envelope,
        `started:${envelope.data.transcript}`,
      );
      setStatus("Finding a grounded match…", "thinking");
      return;
    }
    if (envelope.type === "fast_reply") {
      readyForNewTurn = policy.readyForNewTurn;
      if (policy.showThinkingMessage) {
        assistantMessageForVoice(PENDING_ASSISTANT_MESSAGE, true);
      }
      const fastId = `fast:${envelope.data.transcript}:${envelope.data.answer_text}`;
      if (fastId !== lastFastId) {
        lastFastId = fastId;
        emitEnvelope(envelope, fastId);
      }
      setStatus(
        envelope.data.live_followup_needed
          ? "Checking catalog and current evidence…"
          : "Comparing grounded matches…",
        "thinking",
      );
      return;
    }
    if (envelope.type === "assistant_result") {
      if (policy.showAssistantMessage) {
        assistantMessageForVoice(envelope.data.answer_text);
      }
      emitEnvelope(envelope, resultId);
      readyForNewTurn = policy.readyForNewTurn;
      setStatus("Ready for your next question", "listening");
      elements.voiceHint.textContent = "Keep speaking, or type your next message.";
    }
  } catch (_error) {
    showError("The assistant returned an unreadable update.");
  }
}

function attachRemoteAudio(track) {
  if (track.kind !== Track.Kind.Audio) return;
  track.attach(elements.audio);
  elements.audio.play().catch(() => {
    showError("Use the microphone button once to allow answer audio playback.");
  });
}

function configureRoom(nextRoom) {
  nextRoom.registerTextStreamHandler("lk.transcription", handleTranscription);
  nextRoom
    .on(RoomEvent.TrackSubscribed, attachRemoteAudio)
    .on(RoomEvent.DataReceived, handleProductEvent)
    .on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      const userIsSpeaking = speakers.some(
        (speaker) => speaker.identity === nextRoom.localParticipant.identity,
      );
      if (userIsSpeaking) {
        if (readyForNewTurn) beginVoiceTurn();
        setStatus("Listening…", "listening");
      }
    })
    .on(RoomEvent.Disconnected, () => {
      setStatus("Microphone off", "idle");
      elements.start.classList.remove("hidden");
      elements.stop.classList.add("hidden");
      elements.voiceHint.textContent = "Type a message or start the microphone.";
      endTimer();
    });
}

async function waitForAgent(nextRoom) {
  if (nextRoom.remoteParticipants.size > 0) return;
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      nextRoom.off(RoomEvent.ParticipantConnected, onParticipant);
      reject(new Error("Agent did not join the room"));
    }, 10000);
    const onParticipant = () => {
      clearTimeout(timeout);
      nextRoom.off(RoomEvent.ParticipantConnected, onParticipant);
      resolve();
    };
    nextRoom.on(RoomEvent.ParticipantConnected, onParticipant);
  });
}

async function startConversation() {
  if (!config) return;
  clearError();
  elements.start.disabled = true;
  setStatus("Connecting securely…", "thinking");
  try {
    if (!room || connectedRoom !== config.room_name || room.state === ConnectionState.Disconnected) {
      if (room && room.state !== ConnectionState.Disconnected) await room.disconnect();
      room = new Room({ adaptiveStream: true, dynacast: true });
      configureRoom(room);
      await room.connect(config.server_url, config.token, { autoSubscribe: true });
      connectedRoom = config.room_name;
    }
    await room.startAudio();
    setStatus("Your assistant is joining…", "thinking");
    await waitForAgent(room);
    await room.localParticipant.setMicrophoneEnabled(true);
    beginVoiceTurn();
    elements.start.classList.add("hidden");
    elements.stop.classList.remove("hidden");
    beginTimer();
    setStatus("Listening… start speaking whenever you’re ready", "listening");
    elements.voiceHint.textContent = "Your words will appear in the chat as you speak.";
  } catch (_error) {
    const localHint = config.local
      ? " Start the local LiveKit services, then retry."
      : " Check the LiveKit credentials and agent process.";
    showError(`Could not start the live session.${localHint}`);
    setStatus("Connection failed", "error");
  } finally {
    elements.start.disabled = false;
  }
}

async function stopConversation() {
  if (room) await room.disconnect();
  room = null;
  connectedRoom = null;
  setStatus("Microphone off", "idle");
}

function submitTypedMessage(event) {
  event.preventDefault();
  const text = elements.input.value.trim();
  if (!text) {
    elements.input.focus();
    return;
  }

  clearError();
  const requestId = uniqueId("typed");
  typedTurns.begin(requestId);
  void typedAudio.arm();
  appendMessage("user", text, `user-${requestId}`);
  appendMessage(
    "assistant",
    PENDING_ASSISTANT_MESSAGE,
    `assistant-${requestId}`,
    true,
  );
  elements.input.value = "";
  elements.input.focus();
  setStatus("Finding a grounded match…", "thinking");
  Streamlit.setComponentValue({
    type: "typed_message",
    event_id: requestId,
    data: {
      transcript: text,
      request_id: requestId,
      supports_commit: true,
    },
  });
}

async function restartChat() {
  typedTurns.invalidate();
  if (room) await room.disconnect();
  room = null;
  connectedRoom = null;
  endTimer();
  resetMessages();
  clearError();
  setStatus("Ready to help", "idle");
  elements.start.classList.remove("hidden");
  elements.stop.classList.add("hidden");
  elements.voiceHint.textContent = "Type a message or start the microphone.";
  Streamlit.setComponentValue({
    type: "restart_chat",
    event_id: uniqueId("restart"),
    data: {},
  });
}

async function applyExternalTurn(turn) {
  if (!turn?.request_id || !turn?.answer_text) return;
  const turnEpoch = typedTurns.capture(turn.request_id);
  if (turnEpoch === null) return;
  const signature = `${turn.request_id}:${turn.answer_text}`;
  if (!shouldApplyExternalTurn({
    requestId: turn.request_id,
    pendingRequestId: typedTurns.pendingRequestId(),
    signature,
    lastSignature: lastExternalTurnId,
  })) return;
  lastExternalTurnId = signature;
  await synchronizeTypedTurn(turn, {
    playAudio: (audioBase64) => typedAudio.play(audioBase64),
    isCurrent: (candidate) => typedTurns.isCurrent(
      candidate.request_id,
      turnEpoch,
    ),
    commit: (completedTurn, audioStarted) => {
      if (!typedTurns.complete(completedTurn.request_id, turnEpoch)) return;
      if (completedTurn.transcript) {
        appendMessage(
          "user",
          completedTurn.transcript,
          `user-${completedTurn.request_id}`,
        );
      }
      appendMessage(
        "assistant",
        completedTurn.answer_text,
        `assistant-${completedTurn.request_id}`,
        false,
      );
      if (completedTurn.audio_base64 && !audioStarted) {
        showError(
          "Answer audio could not start. Use “Replay the latest spoken answer” below.",
        );
      }
      setStatus("Ready for your next question", room ? "listening" : "idle");
      const committed = externalTurnCommittedEvent(completedTurn.request_id);
      if (committed) Streamlit.setComponentValue(committed);
    },
  });
}

function onRender(event) {
  config = event.detail.args;
  void applyExternalTurn(config.external_turn);
  Streamlit.setFrameHeight(700);
}

resetMessages();
elements.composer.addEventListener("submit", submitTypedMessage);
elements.restart.addEventListener("click", restartChat);
elements.start.addEventListener("click", startConversation);
elements.stop.addEventListener("click", stopConversation);
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();
Streamlit.setFrameHeight(700);
