# Stonepedia v1 — implementation plan

Vocabulary: [CONTEXT.md](../CONTEXT.md). Decisions: [docs/adr](adr/).

Status (2026-10-21): all six phases are implemented; see the git history for what each delivered. Deviations from this plan: link refresh and audits replaced the "digest" idea once Claude Code became the agent (ADR 0004), Bundles may be one folder of a repository, and the web app also writes machine settings and uploads (never Bundle content).

## Runtime shape

One `docker compose up`, five services from four images:

| Service | Image | Role |
| --- | --- | --- |
| `postgres` | postgres | Temporal persistence + visibility (custom search attributes) |
| `temporal` | temporalio/server | Workflow engine |
| `temporal-ui` | temporalio/ui | Admin/debug console, separate port |
| `web` | stonepedia | FastAPI: serves the React build and a thin API. Talks to Temporal via the client only; reads Bundle repos read-only |
| `worker` | stonepedia (same image) | Temporal worker: extraction, `claude -p`, git |

Volumes: `pgdata`, `bundles` (one git repo per Bundle; worker read-write, web read-only), `config` (machine settings: Claude `settings.json`, default Template, UI locale override).

No separate application database for Proposals. A Proposal *is* a workflow: the Inbox lists it via Temporal visibility (search attributes `Bundle`, `ProposalState`, `ProposalTitle`, `Origin`), and the review screen reads it via a Query and acts via Updates.

## Workflows

- **ProposalWorkflow** (one per Proposal, id `proposal-<ulid>`)
  1. `prepare_source` activity: store original under `sources/<id>/` in a scratch copy of the Bundle, extract text (PDF → per-page text, Office → Markdown, link → fetched HTML → Markdown, image → kept as-is for Claude to read).
  2. `run_agent` activity: `claude -p --settings <config>/claude-settings.json --allowedTools Read,Glob,Grep,Write,Edit` in the scratch copy, with a prompt built from the Template and the Source/Request. Heartbeats; long timeout.
  3. `diff_changes` activity: scratch vs. Bundle HEAD → Article changes (create/update/retire), each with its base blob hash. System-written frontmatter overwritten.
  4. Waits for Updates: `decide(change, accept|discard)`, `edit(change, markdown)`, `revise(change, feedback)`, `feedback(proposal, text)`, `submit()`. Revise/feedback loop back to `run_agent` for undecided changes only.
  5. `submit` → Update to the BundleWorkflow `commit(accepted changes, reviewer)`. Stale changes are refused there and marked stale.
  Uses continue-as-new if revision history grows.
- **BundleWorkflow** (one per Bundle, long-lived): serializes all git writes for that Bundle — commit, regenerate `index.md`/`manifest.json`, assign ids, pull --rebase, push. Push failure leaves the commit local and sets a visible "push paused" state with retry.
- **Maintenance** via Temporal Schedules per Bundle: integrity check (links, frontmatter vs. Template, unreferenced Sources) → report; link-Source refresh → Proposal if content changed; AI audit (manual trigger) → Proposal.

## Agent runner

- Scratch copy = `git worktree` of the Bundle at HEAD, deleted after the diff.
- Prompt = Template (types, fields, sections, guidance) + Bundle language + task (Source paths / Request text / feedback) + rules ("edit existing Articles before creating new ones", "mark assumptions, don't invent values").
- Providers: `claude-cli` (dev and prod) and `fake` (deterministic canned edits for tests and offline UI).
- Worker image installs the Claude Code CLI; the Settings page edits the `settings.json` it is given.

## Web

React + Vite, i18n with `locales/en.json` and `locales/ko.json`, header toggle. Screens: Inbox, New, Proposal review (diff + rendered preview), Bundle (Articles, Sources, Template editor, remote/push status), Maintenance, Settings. Display name prompt on first visit, kept in localStorage.

## Phases

Each phase ends runnable via `docker compose up` and with tests green.

1. **Walking skeleton**: compose stack, empty Bundle creation, New from pasted text, ProposalWorkflow with the `fake` agent, review with Accept/Discard, commit to local git. Inbox via visibility.
2. **Real agent**: `claude-cli` runner and sandbox, Settings page for `settings.json`, Revise/Edit/Proposal feedback, stale detection, system-written frontmatter.
3. **Sources**: PDF, link, image, docx/pptx/xlsx extraction; `sources/<id>/` storage; Requests as attributed statements.
4. **Bundles**: clone existing remote (+ subfolder), remotes and push/rebase, Template editor, id assignment, `index.md`/`manifest.json`, retire, unknown-frontmatter preservation. Verified against a clone of `../knowledge`.
5. **Maintenance**: schedules, integrity report, link refresh, AI audit.
6. **Ship**: Korean locale, `make bundle` offline tar, README (use + deploy in a page).

## Testing

- Workflow tests with the Temporal Python test environment (time-skipping) and the `fake` agent.
- Activity tests for extraction, diffing, frontmatter handling, and git against temp repos.
- One end-to-end smoke test: compose up → create Bundle → submit text → accept → commit present.
- Manual `claude-cli` runs against a copy of `../knowledge/knowledge/bl-kd`.
