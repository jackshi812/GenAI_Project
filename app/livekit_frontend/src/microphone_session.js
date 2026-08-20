async function setMicrophoneEnabled(room, enabled) {
  if (!room) return null;
  await room.localParticipant.setMicrophoneEnabled(enabled);
  return room;
}

export function pauseMicrophone(room) {
  return setMicrophoneEnabled(room, false);
}

export function resumeMicrophone(room) {
  return setMicrophoneEnabled(room, true);
}

