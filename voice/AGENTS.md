# Voice folder brief

This folder is owned and maintained by Jack as part of his end-to-end project ownership.

It contains the small speech-to-text and text-to-speech seams used by the
Streamlit interface. Keep the implementation fragment-based: record a complete
clip, transcribe it, then synthesize a complete answer.

`contracts.py` at the repository root is the single source of truth for shared
data shapes. Import its models; never redefine them here.

Do not log credentials, audio contents, or API keys. Read model and voice
configuration from environment variables. Keep spoken output capped at thirty
words so the demo answer remains within fifteen seconds.

Jack owns changes in this folder and coordinates public interface changes
across the graph and app layers.
