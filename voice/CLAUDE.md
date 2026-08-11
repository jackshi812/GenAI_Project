# Voice folder brief

This folder is owned by Jack.

It contains the small speech-to-text and text-to-speech seams used by the
Streamlit interface. Keep the implementation fragment-based: record a complete
clip, transcribe it, then synthesize a complete answer.

`contracts.py` at the repository root is the single source of truth for shared
data shapes. Import its models; never redefine them here.

Do not log credentials, audio contents, or API keys. Read model and voice
configuration from environment variables. Keep spoken output capped at thirty
words so the demo answer remains within fifteen seconds.

Jack owns changes in this folder. Coordinate any public interface change with
the graph and app owners before changing it.
