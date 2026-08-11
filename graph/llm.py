"""LLM provider selection and prompt loading.

Spec line 149: the model must be swappable through environment variables.
Two env vars, two providers, no registry:

    LLM_PROVIDER=anthropic|openai   (default: anthropic)
    LLM_MODEL=<model name>          (default: claude-opus-5)
"""

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROMPT_CACHE: dict[str, str] = {}

SUPPORTED_PROVIDERS = ("anthropic", "openai")


def get_llm():
    """Return a LangChain chat model selected by LLM_PROVIDER / LLM_MODEL.

    NOTE: never pass a numeric temperature to ChatAnthropic — current Claude
    models reject temperature/top_p/top_k with a 400. temperature=None
    suppresses LangChain's default. Behavior is steered via prompt text.
    """
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    model = os.getenv("LLM_MODEL", "claude-opus-5").strip()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=None, max_tokens=1024)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model)
    raise ValueError(
        f"Unsupported LLM_PROVIDER={provider!r}; supported values are "
        f"{SUPPORTED_PROVIDERS[0]!r} and {SUPPORTED_PROVIDERS[1]!r}."
    )


def load_prompt(name: str) -> str:
    """Read prompts/{name}.md from the repository root, cached.

    Resolved from this file's location, not the process cwd, so
    `python -m graph.smoke` works from anywhere.
    """
    if name not in _PROMPT_CACHE:
        path = _REPO_ROOT / "prompts" / f"{name}.md"
        _PROMPT_CACHE[name] = path.read_text(encoding="utf-8")
    return _PROMPT_CACHE[name]


if __name__ == "__main__":
    provider = os.getenv("LLM_PROVIDER", "anthropic")
    model = os.getenv("LLM_MODEL", "claude-opus-5")
    print(f"provider={provider} model={model}")
    reply = get_llm().invoke("Reply with one short sentence confirming you can hear me.")
    print(reply.content)
