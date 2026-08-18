import test from "node:test";
import assert from "node:assert/strict";

import {
  createTypedTurnEpoch,
  createTypedAudioController,
  synchronizeTypedTurn,
} from "../src/typed_audio.js";

function fakeContext({ advanceOnStart }) {
  const events = [];
  const context = {
    currentTime: 0,
    destination: {},
    state: "suspended",
    async resume() {
      events.push("resume");
      this.state = "running";
    },
    async decodeAudioData(buffer) {
      events.push(`decode:${buffer.byteLength}`);
      return { duration: 1 };
    },
    createBufferSource() {
      const source = {
        buffer: null,
        connect() {
          events.push("connect");
        },
        start(when) {
          events.push("start");
          if (advanceOnStart) context.currentTime = when;
        },
        stop() {
          events.push("stop");
        },
      };
      return source;
    },
  };
  return { context, events };
}

test("typed audio is armed by the send gesture and resolves at audio-clock start", async () => {
  const { context, events } = fakeContext({ advanceOnStart: true });
  const controller = createTypedAudioController({
    contextFactory: () => context,
    decodeBase64: () => "a",
  });

  assert.equal(await controller.arm(), true);
  assert.equal(await controller.play("YQ==", { timeoutMs: 50 }), true);
  assert.deepEqual(events, ["resume", "decode:1", "connect", "start"]);
});

test("typed audio falls back within the bound and stops an unstarted source", async () => {
  const { context, events } = fakeContext({ advanceOnStart: false });
  const controller = createTypedAudioController({
    contextFactory: () => context,
    decodeBase64: () => "a",
  });

  await controller.arm();
  assert.equal(await controller.play("YQ==", { timeoutMs: 5 }), false);
  assert.equal(events.at(-1), "stop");
});

test("a new typed turn stops prior playback before re-arming", async () => {
  const { context, events } = fakeContext({ advanceOnStart: true });
  const controller = createTypedAudioController({
    contextFactory: () => context,
    decodeBase64: () => "a",
  });

  await controller.prepare();
  assert.equal(await controller.play("YQ==", { timeoutMs: 50 }), true);
  const beforePrepare = events.length;
  assert.equal(await controller.prepare(), true);

  assert.deepEqual(events.slice(beforePrepare), ["stop"]);
});

test("stopping a pending typed source settles its stale synchronization wait", async () => {
  const { context } = fakeContext({ advanceOnStart: false });
  const controller = createTypedAudioController({
    contextFactory: () => context,
    decodeBase64: () => "a",
  });

  await controller.prepare();
  const stale = controller.play("YQ==", { timeoutMs: 100 });
  await Promise.resolve();
  controller.stop();

  assert.equal(await stale, false);
});

test("the one final typed response waits for audio start before commit", async () => {
  const commits = [];
  let releaseAudio;
  const turn = {
    request_id: "typed-1",
    answer_text: "Grounded answer.",
    audio_base64: "YQ==",
  };
  const pending = synchronizeTypedTurn(turn, {
    playAudio: () => new Promise((resolve) => {
      releaseAudio = resolve;
    }),
    commit: (value, started) => commits.push([value.request_id, started]),
  });

  await Promise.resolve();
  assert.deepEqual(commits, []);
  releaseAudio(true);
  assert.equal(await pending, true);
  assert.deepEqual(commits, [["typed-1", true]]);
});

test("audio failure still commits exactly one bounded text fallback", async () => {
  const commits = [];
  const turn = {
    request_id: "typed-2",
    answer_text: "Grounded fallback.",
    audio_base64: "bad-audio",
  };

  const started = await synchronizeTypedTurn(turn, {
    playAudio: async () => {
      throw new Error("decode failed");
    },
    commit: (value, audioStarted) => commits.push([value.request_id, audioStarted]),
  });

  assert.equal(started, false);
  assert.deepEqual(commits, [["typed-2", false]]);
});

test("restart invalidates an in-flight typed commit and acknowledgement", async () => {
  const stopped = [];
  const commits = [];
  let releaseAudio;
  const turns = createTypedTurnEpoch({
    stopAudio: () => stopped.push("typed-stop"),
  });
  const turn = {
    request_id: "typed-restart",
    answer_text: "Stale answer.",
    audio_base64: "YQ==",
  };
  const epoch = turns.begin(turn.request_id);
  const pending = synchronizeTypedTurn(turn, {
    playAudio: () => new Promise((resolve) => {
      releaseAudio = resolve;
    }),
    isCurrent: (value) => turns.isCurrent(value.request_id, epoch),
    commit: (value) => commits.push(value.request_id),
  });

  await Promise.resolve();
  turns.invalidate();
  releaseAudio(true);

  assert.equal(await pending, false);
  assert.deepEqual(commits, []);
  assert.deepEqual(stopped, ["typed-stop", "typed-stop"]);
});

test("beginning voice stops typed audio without touching LiveKit audio", async () => {
  let typedStops = 0;
  let livekitStops = 0;
  const commits = [];
  let releaseAudio;
  const turns = createTypedTurnEpoch({
    stopAudio: () => {
      typedStops += 1;
    },
  });
  const turn = {
    request_id: "typed-before-voice",
    answer_text: "Stale typed answer.",
    audio_base64: "YQ==",
  };
  const epoch = turns.begin(turn.request_id);
  const pending = synchronizeTypedTurn(turn, {
    playAudio: () => new Promise((resolve) => {
      releaseAudio = resolve;
    }),
    isCurrent: (value) => turns.isCurrent(value.request_id, epoch),
    commit: (value) => commits.push(value.request_id),
  });

  await Promise.resolve();
  turns.invalidate();
  releaseAudio(true);
  await pending;

  assert.equal(typedStops, 2);
  assert.equal(livekitStops, 0);
  assert.deepEqual(commits, []);
});
