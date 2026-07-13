"""Parsing agents' final JSON answers - every real agent in Day 4 is
instructed to end with a bare JSON object, this is the one place that
parses it so a formatting slip doesn't get reimplemented five different ways.
"""

import json
import re


def parse_json_final(text: str | None) -> dict:
    if not text:
        return {"error": "empty response", "raw": text}
    stripped = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"error": "could not parse JSON", "raw": text}
