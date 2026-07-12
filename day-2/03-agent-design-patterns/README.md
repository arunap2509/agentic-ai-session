# Agent Design Patterns

Nine small, standalone scripts — one per pattern. Each "agent" is just the
same Gemini model called with a different prompt; the point is the
control-flow shape, not the model itself.

| Script | Pattern |
|---|---|
| `01_react.py` | ReAct — the atomic loop |
| `02_reflection.py` | Reflection — one agent, two hats |
| `03_planning.py` | Planning — full plan before execution |
| `04_human_in_the_loop.py` | Human-in-the-Loop |
| `05_sequential.py` | Sequential (multi-agent) |
| `06_routing.py` | Routing (multi-agent) |
| `07_parallelization.py` | Parallelization (multi-agent) |
| `08_orchestrator_workers.py` | Orchestrator-Workers (multi-agent) |
| `09_evaluator_optimizer.py` | Evaluator-Optimizer (multi-agent) |

Run any of them directly:

```bash
python 01_react.py
python 02_reflection.py
# ...etc
```

## Talking points per script

- **01_react** — same tool-use loop shape as the tools demo, but the
  prints use the words Thought / Action / Observation to make the loop
  explicit.
- **02_reflection** — ONE agent drafts, then the SAME model switches into
  critic mode. Capped at 3 revision rounds.
- **03_planning** — the plan (ordered step list) is built in one call
  *before* any execution starts, then each step runs against that fixed
  plan. Contrast with Orchestrator-Workers, where the split is dynamic.
- **04_human_in_the_loop** — interactive: the second request is
  classified high-risk and the script actually pauses on `input()` for a
  live approve/decline.
- **05_sequential** — Agent A (outline) -> Agent B (draft) -> Agent C
  (edit), each one's output is the next one's input.
- **06_routing** — a classifier call picks billing / technical / general,
  then dispatches to a differently-prompted specialist.
- **07_parallelization** — three subagents run concurrently via
  `asyncio.gather`; the script prints how long the concurrent run took as
  proof they weren't sequential, then merges the results.
- **08_orchestrator_workers** — the orchestrator decides *at runtime* how
  many workers it needs and what each should do (not a fixed step list),
  workers run independently, then the orchestrator synthesizes.
- **09_evaluator_optimizer** — TWO separate agents: a Generator that
  produces attempts and an Evaluator that only judges against explicit
  criteria and never edits. Failing feedback loops back to the Generator.
