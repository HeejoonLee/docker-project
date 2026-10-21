# Development notes

## Layout

| Path | What |
| --- | --- |
| `src/stonepedia/workflows.py` | Temporal workflows: `BundleWorkflow` (one per Bundle; serializes git writes, pushes), `ProposalWorkflow` (one per Proposal; agent runs, review updates, commit), `MaintenanceWorkflow`, `AgentCheckWorkflow` |
| `src/stonepedia/activities.py` | Everything with side effects: git, files, the agent, Source extraction |
| `src/stonepedia/web.py` | FastAPI. Talks to Temporal only through the client; reads Bundle repos to display them; writes only machine settings and uploads |
| `src/stonepedia/agent/` | `claude -p` runner, prompt builder, fake agent |
| `src/stonepedia/bundle.py` | Bundle folder rules: settings, Template, ids, index/manifest |
| `src/stonepedia/sources.py` | Source extraction (PDF, Office, HTML, links, images) |
| `src/stonepedia/maintenance.py` | Integrity checks |
| `web/` | React UI; strings in `web/src/locales/{en,ko}.json` |

There is no application database. Proposals, Bundles, maintenance runs and schedules are Temporal workflows and schedules; Bundle content is git.

## Changing workflow code

Temporal replays a workflow's history through the current code. Running workflows (open Proposals and every Bundle) break if a change alters the sequence of activities, timers or child workflows they already recorded. During development, the fix was to wipe the dev data. On a deployed server, that is not an option.

Once deployed:

- Use `workflow.patched("change-name")` around changed command sequences in `ProposalWorkflow`, `BundleWorkflow` and `MaintenanceWorkflow`, and keep the old branch until no running workflow needs it. `BundleWorkflow` runs forever (continue-as-new), so this matters most there.
- Adding fields with defaults to models, adding update/query handlers, and changing activity internals are safe.
- If a release cannot keep open Proposals, say so in the release notes (INSTALL.md tells operators to read them).

## Tests

`make test` starts a local Temporal dev server through the Temporal CLI and uses the fake agent (the `agent="fake"` test setting; `STONEPEDIA_AGENT=fake` does the same for a running stack, e.g. to click through the UI offline); the Claude runner is tested against a stub binary. One test imports `../knowledge` when that repo exists next to this one.
