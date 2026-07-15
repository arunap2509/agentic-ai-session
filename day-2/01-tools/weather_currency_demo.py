"""
Tools & Agent SDK - two tools, several ways the model can use them
=================================================================

Same idea as the OpenAI-style tool list below, written as Gemini tools:

    tools = [
        {"type": "function", "function": {
            "name": "get_current_weather",
            "description": "Get the current weather for a given city, including temperature and precipitation",
            "parameters": {"type": "object", "properties": {
                "city": {"type": "string"}, "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            }, "required": ["city"]},
        }},
        {"type": "function", "function": {
            "name": "convert_currency",
            "description": "Convert an amount from one currency to another",
            "parameters": {"type": "object", "properties": {
                "amount": {"type": "number"}, "from_currency": {"type": "string"}, "to_currency": {"type": "string"}
            }, "required": ["amount", "from_currency", "to_currency"]},
        }},
    ]

In Gemini's SDK the same contract is built from a plain Python function via
types.FunctionDeclaration.from_callable() - the type hints and docstring
become the schema, same information, different shape.

Example prompts to try (see README.md for what each one demonstrates):
  1. I bet my friend 100 EUR that it would rain in Athens today. If I won, how many USD is that?
  2. What's the weather in Athens and how much is 100 USD in EUR?
  3. What's the weather in Athens?
  4. How much is 100 USD in EUR?
  5. I bet my friend 100 EUR that it would rain in Rome today. If I won, how many USD is that?
  6. What's the weather in Athens and Rome?

Run:
    python weather_currency_demo.py
    (then type a prompt at the "prompt: " input, empty line to quit)
"""

import sys
from pathlib import Path

from google.genai import types
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()

FAKE_WEATHER = {
    "athens": {"condition": "light rain", "temp_c": 19},
    "rome": {"condition": "clear skies", "temp_c": 24},
}

FAKE_RATES = {
    ("EUR", "USD"): 1.09,
    ("USD", "EUR"): 0.92,
}

SYSTEM_INSTRUCTION = (
    "If a request assumes some fact you have not actually checked, verify "
    "that fact with a tool before acting on it - don't assume it's true. "
    "Only call a tool that depends on that fact once you've confirmed it."
)


def get_current_weather(city: str, unit: str = "celsius") -> dict:
    """Get the current weather for a given city, including temperature and precipitation.

    Args:
        city: The name of the city.
        unit: Temperature unit, "celsius" or "fahrenheit".
    """
    data = FAKE_WEATHER.get(city.strip().lower())
    if data is None:
        return {"error": f"no weather data for '{city}'"}
    temp_c = data["temp_c"]
    temp = temp_c if unit == "celsius" else round(temp_c * 9 / 5 + 32, 1)
    return {"city": city, "condition": data["condition"], "temperature": temp, "unit": unit}


def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert an amount from one currency to another.

    Args:
        amount: The amount to convert.
        from_currency: The source currency code, e.g. EUR.
        to_currency: The target currency code, e.g. USD.
    """
    key = (from_currency.strip().upper(), to_currency.strip().upper())
    rate = FAKE_RATES.get(key)
    if rate is None:
        return {"error": f"no rate for {key[0]} -> {key[1]}"}
    return {
        "amount": amount,
        "from_currency": key[0],
        "to_currency": key[1],
        "rate": rate,
        "converted": round(amount * rate, 2),
    }


TOOL_REGISTRY = {
    "get_current_weather": get_current_weather,
    "convert_currency": convert_currency,
}


def build_tools(client) -> types.Tool:
    declarations = [
        types.FunctionDeclaration.from_callable(client=client, callable=fn)
        for fn in TOOL_REGISTRY.values()
    ]
    return types.Tool(function_declarations=declarations)


def run_tool_loop(prompt: str, max_steps: int = 6) -> None:
    client = get_client()
    tool = build_tools(client)

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=prompt)])
    ]

    console.print(f"user: {prompt}")

    for step in range(1, max_steps + 1):
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[tool], system_instruction=SYSTEM_INSTRUCTION
            ),
        )
        candidate_content = response.candidates[0].content
        contents.append(candidate_content)

        function_calls = response.function_calls

        console.print(f"\nmodel response, step {step}:")
        console.print(f"  content: {response.text!r}")
        if function_calls:
            console.print(
                "  tool_calls: "
                + str([{"name": c.name, "args": dict(c.args)} for c in function_calls])
            )
        else:
            console.print("  tool_calls: None")

        if not function_calls:
            return

        response_parts = []
        for call in function_calls:
            handler = TOOL_REGISTRY[call.name]
            result = handler(**call.args)
            console.print(f"  tool result for {call.name} (id={call.id}): {result}")
            # call.id (not just name) must round-trip on the response: if the
            # model makes two calls to the same tool in one turn (e.g.
            # get_current_weather for two cities), name alone can't tell them
            # apart - id is what pairs each response to the right call.
            response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        id=call.id, name=call.name, response={"result": result}
                    )
                )
            )

        contents.append(types.Content(role="user", parts=response_parts))

    raise RuntimeError(f"did not finish within {max_steps} steps")


if __name__ == "__main__":
    while True:
        try:
            prompt = input("prompt: ").strip()
        except EOFError:
            break
        if not prompt:
            break
        run_tool_loop(prompt)
        console.print()
