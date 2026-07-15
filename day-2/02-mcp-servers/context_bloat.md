How real systems deal with this — MCP doesn't solve it, the host has to add a
  layer on top:
  1. Static curation — a human decides ahead of time which subset of tools this
  agent actually needs and only mounts those, rather than forwarding an entire
  server's catalog.
  2. Progressive disclosure — the model first sees only a short list of tool names
  (no full schemas), calls a meta-tool like "load this tool's schema," and only
  then does the real schema get injected for follow-up calls. This is exactly
  what's happening in this very conversation: tools like CronCreate or WebSearch
  show up to me as bare names, and I have to call ToolSearch to pull in the full
  schema before I can use them — that's the pattern you're describing, and it
  exists precisely to avoid the bloat you're pointing at.
  3. Semantic tool search — for very large tool counts, index tool descriptions and
  retrieve only the top few relevant ones per query.