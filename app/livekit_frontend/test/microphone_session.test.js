import assert from "node:assert/strict";
import test from "node:test";

import {
  pauseMicrophone,
  resumeMicrophone,
} from "../src/microphone_session.js";

test("stop then start toggles the microphone without leaving the LiveKit room", async () => {
  const microphoneStates = [];
  let disconnects = 0;
  const room = {
    localParticipant: {
      async setMicrophoneEnabled(enabled) {
        microphoneStates.push(enabled);
      },
    },
    async disconnect() {
      disconnects += 1;
    },
  };

  const pausedRoom = await pauseMicrophone(room);
  const resumedRoom = await resumeMicrophone(pausedRoom);

  assert.equal(pausedRoom, room);
  assert.equal(resumedRoom, room);
  assert.deepEqual(microphoneStates, [false, true]);
  assert.equal(disconnects, 0);
});

