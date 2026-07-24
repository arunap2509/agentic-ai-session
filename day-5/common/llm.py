"""Shared Gemini client setup, reused by both projects in Day 5."""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

# Explicit context caching (see prompt-caching/) needs a model whose account
# grant still includes createCachedContent - pinned versions like
# "gemini-2.5-flash" can 404 with "no longer available to new users" even
# though `models.list()` still advertises the capability, depending on when
# your API key was created. "gemini-flash-latest" has been reliable in
# testing; override here if your key needs something else.
CACHE_MODEL = os.environ.get("GEMINI_CACHE_MODEL", "gemini-flash-latest")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Copy day-5/.env.example to day-5/.env and add "
            "the same key used in earlier days, from https://aistudio.google.com/apikey"
        )
    _client = genai.Client(api_key=api_key)
    return _client
