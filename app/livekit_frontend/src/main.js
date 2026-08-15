import { Streamlit } from "streamlit-component-lib";
import {
  ConnectionState,
  Room,
  RoomEvent,
  Track,
} from "livekit-client";
import "./style.css";

const elements = {
  answer: document.getElementById("answer"),
  answerPanel: document.getElementById("answer-panel"),
  audio: document.getElementById("agent-audio"),
  error: document.getElementById("error"),
  start: document.getElementById("start"),
  stateDot: document.getElementById("state-dot"),
  status: document.getElementById("status"),
  stop: document.getElementById("stop"),
  timer: document.getElementById("timer"),
  transcript: document.getElementById("transcript"),
  visualizer: document.getElementById("visualizer"),
};

let config = null;
let room = null;
let connectedRoom = null;
let startedAt = null;
let timerHandle = null;
let lastResultId = null;
let readyForNewTurn = false;
const userSegments = new Map();

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

function renderTranscript() {
  const text = [...userSegments.values()]
    .map((segment) => segment.text)
    .filter(Boolean)
    .join(" ")
    .trim();
  elements.transcript.textContent = text || "Listening…";
  elements.transcript.classList.toggle("muted", !text);
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
}

async function handleTranscription(reader, participantInfo) {
  const message = (await reader.readAll()).trim();
  const attributes = reader.info?.attributes || {};
  const segmentId = attributes["lk.segment_id"] || `${Date.now()}`;
  const isFinal = attributes["lk.transcription_final"] === "true";
  const isUser = participantInfo.identity === room?.localParticipant.identity;

  if (isUser) {
    userSegments.set(segmentId, { text: message, final: isFinal });
    renderTranscript();
    setStatus(isFinal ? "Finding a grounded match…" : "Listening…", isFinal ? "thinking" : "listening");
  }
}

function handleProductEvent(payload, _participant, _kind, topic) {
  if (topic !== "product.discovery") return;
  try {
    const envelope = JSON.parse(new TextDecoder().decode(payload));
    if (envelope.type === "fast_reply") {
      elements.answer.textContent = envelope.data.answer_text;
      elements.answerPanel.classList.remove("hidden");
      readyForNewTurn = true;
      setStatus(
        envelope.data.live_followup_needed
          ? "Speaking now; checking current web evidence in the background…"
          : "Speaking…",
        "speaking",
      );
      return;
    }
    if (envelope.type === "assistant_result") {
      const resultId = `${envelope.data.transcript}:${envelope.data.answer_text}`;
      if (resultId !== lastResultId) {
        lastResultId = resultId;
        Streamlit.setComponentValue(envelope);
      }
      setStatus("Ready for your next question", "listening");
    }
  } catch (error) {
    showError("The assistant returned an unreadable update.");
  }
}

function attachRemoteAudio(track) {
  if (track.kind !== Track.Kind.Audio) return;
  track.attach(elements.audio);
  elements.audio.play().catch(() => {
    showError("Tap Start conversation again to allow answer audio playback.");
  });
}

function configureRoom(nextRoom) {
  nextRoom.registerTextStreamHandler("lk.transcription", handleTranscription);
  nextRoom
    .on(RoomEvent.TrackSubscribed, attachRemoteAudio)
    .on(RoomEvent.DataReceived, handleProductEvent)
    .on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      if (speakers.some((speaker) => speaker.identity === nextRoom.localParticipant.identity)) {
        if (readyForNewTurn) {
          userSegments.clear();
          renderTranscript();
          elements.answerPanel.classList.add("hidden");
          readyForNewTurn = false;
        }
        setStatus("Listening…", "listening");
      }
    })
    .on(RoomEvent.Disconnected, () => {
      setStatus("Conversation ended", "idle");
      elements.start.classList.remove("hidden");
      elements.stop.classList.add("hidden");
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
    userSegments.clear();
    renderTranscript();
    elements.answerPanel.classList.add("hidden");
    elements.start.classList.add("hidden");
    elements.stop.classList.remove("hidden");
    beginTimer();
    setStatus("Listening… start speaking whenever you’re ready", "listening");
  } catch (error) {
    const localHint = config.local
      ? " Start `livekit-server --dev` and the voice agent, then retry."
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
  setStatus("Conversation ended", "idle");
}

function onRender(event) {
  config = event.detail.args;
  Streamlit.setFrameHeight(430);
}

elements.start.addEventListener("click", startConversation);
elements.stop.addEventListener("click", stopConversation);
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();
Streamlit.setFrameHeight(430);
