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

## `weather_currency_demo.py`

Two tools, `get_current_weather` and `convert_currency`, both RETRIEVE
(no execute/confirmation concerns like `send_email` above). Every model
turn prints its `content` and `tool_calls` exactly as the model returned
them, so you can see the same content=None / tool_calls=[...] pattern
that tool-calling APIs use, whichever prompt you give it.

```bash
source ../.venv/bin/activate   # if not already active
python weather_currency_demo.py
```

It prompts for input on the console (`prompt: `), so you can type any of
these to show a different shape of the tool-use loop, then an empty line
to quit:

1. `I bet my friend 100 EUR that it would rain in Athens today. If I won, how many USD is that?`
   Meant to be sequential: `get_current_weather` must be checked before
   deciding whether `convert_currency` is even needed. The script's
   `system_instruction` states this as a general rule — verify a fact with a
   tool before acting on it, don't assume it — rather than naming these two
   tools specifically, so it still holds if more tools get added later.
   Without it, the model would sometimes skip straight to `convert_currency`
   and just assume the bet was won, wasting a call whenever it turns out not
   to have rained. This is bias, not a guarantee — the model can still
   choose to call both in one turn.
2. `What's the weather in Athens and how much is 100 USD in EUR?`
   Parallel: both questions are independent, so the model typically
   requests both tool calls in a single turn.
3. `What's the weather in Athens?`
   Single tool, single call.
4. `How much is 100 USD in EUR?`
   Single tool, single call, no weather involved.
5. `I bet my friend 100 EUR that it would rain in Rome today. If I won, how many USD is that?`
   Same as (1) but Rome is fake-clear, not rainy — shows the condition
   turning out false, so `convert_currency` should not be called at all.
6. `What's the weather in Athens and Rome?`
   Two calls to the *same* tool (`get_current_weather`) in one turn. Each
   `FunctionCall` the model returns carries an `id`; the script echoes that
   same `id` back on each `FunctionResponse` so the two results can't be
   mixed up. Matching on `name` alone wouldn't be enough here since both
   calls share the same tool name.

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
