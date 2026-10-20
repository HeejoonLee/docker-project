# The proposing agent is Claude Code in headless mode, sandboxed to a scratch copy of the Bundle

Proposals are written by `claude -p`, not by direct LLM API calls: Claude Code explores the Bundle and Source files with its own tools and writes Articles, which proved better than a bare model behind a hand-built retrieval pipeline. The model backend is whatever the operator's Claude settings file (edited on the web Settings page, passed via `--settings`) points to — at the company, an internal LLM. Each run works in a throwaway copy of the Bundle repo with only file tools (no shell, no web; links are fetched by Stonepedia beforehand); Stonepedia derives Article changes from the resulting diff and overwrites system-written frontmatter, so the agent can never change the real repository.

## Considered Options

- Direct OpenAI-compatible API calls with index-then-read retrieval and chunked Source digests — dropped as more code for a weaker agent.
