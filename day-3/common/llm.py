"""Shared Gemini client setup used by every stage in data-analyst-agent."""

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
            "GEMINI_API_KEY not set. Copy day-3/.env.example to day-3/.env and add "
            "a key from https://aistudio.google.com/apikey"
        )
    _client = genai.Client(api_key=api_key)
    return _client
