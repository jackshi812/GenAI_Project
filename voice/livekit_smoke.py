"""Local LiveKit smoke test for fast reply data and first answer audio."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from livekit import rtc
from openai import OpenAI

from app.livekit_component import (
    create_room_token,
    new_room_name,
    settings_from_env,
)


QUERY = "Compare the current Nerf Strongarm price with the catalog price."
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def run_smoke() -> dict[str, int]:
    settings = settings_from_env()
    room_name = new_room_name()
    token = create_room_token(
        settings,
        room_name=room_name,
        identity="smoke-shopper",
    )
    room = rtc.Room()
    agent_joined = asyncio.Event()
    interim_transcript = asyncio.Event()
    fast_reply = asyncio.Event()
    first_audio = asyncio.Event()
    speech_finished = asyncio.Event()
    timestamps: dict[str, float] = {}

    async def handle_transcription(
        reader: rtc.TextStreamReader,
        participant_identity: str,
    ) -> None:
        message = (await reader.read_all()).strip()
        attributes = reader.info.attributes or {}
        if (
            participant_identity == "smoke-shopper"
            and message
            and attributes.get("lk.transcription_final") == "false"
        ):
            interim_transcript.set()

    def on_transcription(
        reader: rtc.TextStreamReader,
        participant_identity: str,
    ) -> None:
        asyncio.create_task(handle_transcription(reader, participant_identity))

    room.register_text_stream_handler("lk.transcription", on_transcription)

    @room.on("participant_connected")
    def on_participant_connected(_participant: rtc.RemoteParticipant) -> None:
        agent_joined.set()

    @room.on("data_received")
    def on_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic != "product.discovery":
            return
        envelope = json.loads(packet.data.decode("utf-8"))
        if envelope.get("type") == "fast_reply":
            timestamps["fast_reply"] = time.perf_counter()
            fast_reply.set()

    @room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        _publication: rtc.RemoteTrackPublication,
        _participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return

        async def receive_first_frame() -> None:
            stream = rtc.AudioStream.from_track(track=track)
            try:
                async for event in stream:
                    if not speech_finished.is_set():
                        continue
                    samples = event.frame.data
                    if samples and max(abs(value) for value in samples[::8]) > 100:
                        timestamps["first_audio"] = time.perf_counter()
                        first_audio.set()
                        break
            finally:
                await stream.aclose()

        asyncio.create_task(receive_first_frame())

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    speech = await asyncio.to_thread(
        lambda: OpenAI(api_key=api_key).audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=QUERY,
            response_format="pcm",
        ).content
    )

    await room.connect(settings.url, token)
    try:
        await asyncio.wait_for(agent_joined.wait(), timeout=10)
        sample_rate = 24_000
        samples_per_frame = sample_rate // 100
        bytes_per_frame = samples_per_frame * 2
        source = rtc.AudioSource(sample_rate, 1)
        track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
        await room.local_participant.publish_track(
            track,
            rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
        )

        for offset in range(0, len(speech), bytes_per_frame):
            chunk = speech[offset : offset + bytes_per_frame]
            chunk = chunk.ljust(bytes_per_frame, b"\0")
            await source.capture_frame(
                rtc.AudioFrame(
                    chunk,
                    sample_rate,
                    1,
                    samples_per_frame,
                )
            )
            await asyncio.sleep(0.01)

        timestamps["speech_finished"] = time.perf_counter()
        speech_finished.set()
        silence = b"\0" * bytes_per_frame
        for _ in range(70):
            await source.capture_frame(
                rtc.AudioFrame(
                    silence,
                    sample_rate,
                    1,
                    samples_per_frame,
                )
            )
            await asyncio.sleep(0.01)

        await asyncio.wait_for(interim_transcript.wait(), timeout=3)
        await asyncio.wait_for(fast_reply.wait(), timeout=5)
        reply_ms = round(
            (timestamps["fast_reply"] - timestamps["speech_finished"]) * 1_000
        )
        await asyncio.wait_for(first_audio.wait(), timeout=8)
        audio_ms = round(
            (timestamps["first_audio"] - timestamps["speech_finished"]) * 1_000
        )
        return {
            "interim_transcript_while_speaking": 1,
            "fast_reply_ms": reply_ms,
            "first_audio_ms": audio_ms,
        }
    finally:
        await room.disconnect()


def main() -> None:
    print(json.dumps(asyncio.run(run_smoke()), separators=(",", ":")))


if __name__ == "__main__":
    main()
