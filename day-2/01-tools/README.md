# Tools & Agent SDK

## `tool_calling_demo.py`

One script, three talking points:

1. **The schema is a contract** — prints the exact JSON schema Gemini
   receives for each tool before any call happens.
2. **RETRIEVE vs EXECUTE** — `get_weather` is a low-stakes lookup,
   `send_email` is a mocked but higher-stakes action. Note how explicit
   `send_email`'s docstring is about what it does and does NOT do (single
   recipient only, no cc/bcc/attachments, no confirmation step, sends
   immediately) — a vague description here is exactly what causes an
   agent to misuse a tool in production.
3. **The tool-use loop** — the loop is written out manually (not using the
   SDK's automatic function calling) so every Action / Observation step
   prints as it happens.

```bash
source ../.venv/bin/activate   # if not already active
python tool_calling_demo.py
```

The `__main__` prompt asks about a specific city. Weather data is faked
for `paris` and `london` (rainy/overcast — triggers the EXECUTE path,
`send_email`) and `bengaluru` (sunny — the model just answers, no email).
Swap the city to show either path live.

## `date_grounding_demo.py`

Asks the same date-dependent question twice: once with no tools, once
with a `get_current_date` tool. Without the tool the model doesn't refuse
or hedge — it states a specific, wrong date with full confidence. With the
tool, it calls it and gets the real answer. Good for making the point that
grounding isn't optional politeness, it's the difference between a
confident wrong answer and a correct one.

```bash
python date_grounding_demo.py
```
