"""Shared Gemini client setup, reused by every agent in both Day 4 projects."""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
TRIAGE_MODEL = os.environ.get("GEMINI_TRIAGE_MODEL", "gemini-flash-lite-latest")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Copy day-4/.env.example to day-4/.env and add "
            "the same key used in day-3, from https://aistudio.google.com/apikey"
        )
    _client = genai.Client(api_key=api_key)
    return _client
