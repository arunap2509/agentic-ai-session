"""Shared Gemini client setup used by every demo in day-2."""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Copy day-2/.env.example to day-2/.env and add "
            "a key from https://aistudio.google.com/apikey"
        )
    _client = genai.Client(api_key=api_key)
    return _client


def ask(prompt: str, system: str | None = None) -> str:
    """One-shot text generation. Used by the design-pattern demos, where each
    'agent' is just a differently-prompted call to the same model."""
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    response = get_client().models.generate_content(model=MODEL, contents=prompt, config=config)
    return response.text


async def ask_async(prompt: str, system: str | None = None) -> str:
    """Async version of ask(), for patterns that fan out multiple calls at once."""
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    response = await get_client().aio.models.generate_content(
        model=MODEL, contents=prompt, config=config
    )
    return response.text
