# Coding Agent

The third contrast in day-3. Data Analyst Agent is **depth** (one agent,
adaptive investigation). Ticker Triaging Agent is **breadth** (a fixed
pipeline over many events). This one is **side effects**: instead of
read-only tools, `write_file` and `run_python` actually change the
filesystem and actually execute code - the loop's observation isn't a
query result, it's real stdout/stderr from a real run.

Same `run_tool_loop` from `common/agent_loop.py`, no changes needed there -
tool-calling doesn't care whether a tool reads or writes.

Every `write_file` call also prints a colorized unified diff against
whatever was there before (seeded from the original buggy file, if you
pointed it at one) - so instead of re-reading a full file dump each
iteration, you see exactly what the model changed, and how many times it
touched the file before landing on something that actually ran clean.

## The one rule that matters

`SYSTEM_INSTRUCTION` forbids declaring the task done without a
`run_python` observation showing `exit_code 0` *and* output that actually
satisfies the task. Same grounding idea as `data-analyst-agent`'s
`GROUNDED_INSTRUCTION`: writing a file is not evidence it works, only
running it is. Without this rule there's nothing stopping the model from
writing plausible-looking broken code and just claiming success.

## Run it

```bash
python coding_agent.py
```

Two prompts for the first task, in order:
1. **Existing buggy file to fix** (a path on your machine - blank to skip
   and write from scratch instead). If given, it's copied into
   `workspace/` under its own filename before the agent starts.
2. **Task** - what it should do, or what's wrong with it.

After that task finishes, it doesn't exit - it keeps prompting for a
**Next instruction**, applied to the same file(s), in the same
conversation. This isn't a fresh, context-free run each time - `contents`
(the full turn history) is threaded from one call into the next, so a
follow-up like "also add a test for the empty-string case" lands on top
of what it already wrote, and it re-verifies with `run_python` the same
way as the first task. Blank instruction to quit.

Execution is real (via `subprocess`, confined to `workspace/`, 10s
timeout, no stdin) - fine for this demo, not a hardened sandbox.

## Things worth trying

- **From scratch:** blank first prompt, task like "write a function that
  returns the nth Fibonacci number, plus a few print statements testing
  it for n = 0, 1, 10". Watch it verify its own test output before
  stopping.
- **A real bug to fix:** write a small buggy `.py` file yourself first
  (off-by-one, wrong operator, unhandled edge case, an import typo) and
  point the first prompt at it. Compare how many loop iterations a
  syntax error takes to fix vs. a logic error that runs cleanly but
  produces the wrong answer - the second kind requires the model to
  actually reason about whether the *output* is right, not just whether
  it ran.
- **Vague vs. specific tasks:** the same bug description phrased loosely
  ("this doesn't work right") vs. precisely ("this raises IndexError when
  the list is empty") - watch whether loop count and the model's own
  Thought narration change.
- **Loop count as a signal:** the printed `(N run_python attempt(s))` at
  the end is the whole story of how hard the task was - 1 attempt means
  it got it right first try, several means real iteration happened. Worth
  comparing across the above scenarios rather than just reading the final
  answer.
- **Follow-up instructions:** after the first task lands, add something
  incremental ("also handle the empty string case", "now make it print
  PASS/FAIL instead of True/False") and watch the diff - it should only
  show the new change, not a full rewrite, because the model still has
  the whole prior conversation as context.
