"""
Structured Output - JSON mode and schema-constrained JSON
===========================================================

Gemini's equivalent of OpenAI's response_format={"type": "json_object"}
is a couple of fields on GenerateContentConfig instead of a separate flag.

Two ways to use it below - comment out whichever one you're not demoing:
  1. Raw JSON mode - response_mime_type only, no schema, model picks the shape.
  2. Structured output - response_mime_type + response_schema (a Pydantic
     model), so the JSON is guaranteed to match that shape.

Run:
    python structured_output_demo.py
"""

import sys
from pathlib import Path

from google.genai import types
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

client = get_client()

# --- 1. Structured output (Pydantic schema) -----------------------------

class Apple(BaseModel):
    name: str
    color: str
    taste_profile: str


class AppleList(BaseModel):
    apples: list[Apple]


config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=AppleList,
)

response = client.models.generate_content(
    model=MODEL,
    contents="Give me information on 3 popular apple varieties.",
    config=config,
)
print(response.text)
