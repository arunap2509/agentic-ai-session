Here is exactly what the raw output of the LLM looks like before the API server processes it, and how the two pieces work together.

---

### 1. What the Actual LLM Response Looks Like

Inside the data center, the actual LLM doesn't know about HTTP protocols, API status codes, or your SDK's object models. It only processes and outputs a **continuous stream of raw tokens (text fragments)**.

Depending on what the model decides to do, its raw, native output stream looks fundamentally different:

#### Scenario A: If it's just generating standard text

The model's neural network simply fires off tokens sequentially until it hits an `<End of Sequence>` (EOS) token.

* **The raw LLM output:** `Sure, I can help you with that! The capital of France is Paris.<EOS>`

#### Scenario B: If it's triggering a Tool/Function Call

The model switches to constrained decoding. The neural network explicitly writes out text tokens that form a syntax structure.

* **The raw LLM output:** `{"name": "get_order_status", "args": {"order_id": "1042"}}<EOS>`

> ⚠️ **Key Realization:** Notice that even when it calls a tool, the raw LLM output is still just a long text string! The model doesn't output a programming language object; it literally outputs the characters `{`, `"`, `n`, `a`, `m`, `e`, and so on.

---

### 2. How the API Server "Envelopes" the Response

Once the LLM hits its `<EOS>` token and finishes generating, the API server software (written in a language like Go, C++, or Python running on the provider's backend infrastructure) takes over.

The API server's job is to act as the postal service: it takes that raw string from the model, determines what kind of text it is, and packages it into the rigid, uniform HTTP JSON structure your SDK expects.

Here is how the API server translates those raw streams:

```
[Raw LLM Output Stream] ───────────────────> [API Server Layer] ───────────────────> [Final Network JSON Payload]

"Sure, I can help you..."                   API sees it's plain text.              { "candidates": [{ "content": { "parts": [{ "text": "Sure, I can help..." }] }}]}
                                            It maps it to the "text" key.

"{"name": "get_order_status", ...}"        API parses this text string as JSON.   { "candidates": [{ "content": { "parts": [{ "functionCall": { "name": "...", "args": {...} } }] }}]}
                                            It maps it to the "functionCall" key.

```

---

### The Big Picture Architecture

To visualize the entire lifecycle of how your request travels through the infrastructure:

```
[Your App / SDK] 
       │  ▲
       │  │ (Uniform HTTP JSON Envelope)
       ▼  │
┌────────────────────────────────────────────────────────┐
│ PROVIDER'S BACKEND SERVER (The API Layer)              │
│  • Manages authentication, logging, and rate limits.   │
│  • Packages the final output into the strict API JSON. │
└──────────────────────────┬─────────────────────────────┘
                           │  ▲
                           │  │ (Raw Text/Token Streams)
                           ▼  │
┌────────────────────────────────────────────────────────┐
│ THE LLM NEURAL NETWORK (The Core Brain)                │
│  • Simply runs matrix multiplications on GPU clusters. │
│  • Spits out character tokens one by one.              │
└────────────────────────────────────────────────────────┘

```

Constrained decoding (also known as guided generation or structured generation) is a technique used to force a Large Language Model to output text that follows a specific, predefined format—such as valid JSON, SQL, XML, or a specific regular expression (regex).

Without constrained decoding, an LLM relies on its training to "guess" how to format things, which frequently leads to syntax errors, missing brackets, or unwanted conversational prose like "Sure, here is the JSON you asked for:".

With constrained decoding, it is physically impossible for the model to break the specified structure.