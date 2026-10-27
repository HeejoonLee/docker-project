# Reference directories and repository imports

## Behavior

- Git remotes accept HTTP(S), scp-style SSH, and `ssh://` URLs. Gerrit ports use the explicit form `ssh://user@host:29418/project.git`. The Docker worker uses a server-managed SSH key, config, and `known_hosts`; Git must fail without prompting if authentication or host verification fails.
- A deployment exposes one host parent directory to the worker at `/references`, read-only. Each Bundle selects a directory beneath it. The reference stays outside the Bundle and is available to all its Proposals.
- A reviewer can start a code-only Proposal with a required focus instruction, or use the reference as background for another Proposal. Plain directories and Git worktrees with uncommitted files are allowed.
- Accepted Articles record the relative paths and SHA-256 hashes of code files used as evidence, plus a Git commit when available. Source code is neither uploaded nor committed to the Bundle.
- Only changes to cited code files make a Proposal stale. A stale Proposal must be explicitly refreshed against the current code before it can be revised or accepted.
- Each Bundle has editable exclusion patterns, with defaults for `.git`, `.env*`, `node_modules`, `.venv`, `dist`, and `build`. The agent reads the mounted directory directly; exclusions guide discovery and do not prevent access to a known path.
- Importing a repository with OKF v0.2 frontmatter leaves existing Article files untouched. Stonepedia infers the Template and an unambiguous existing ID scheme, and shows compatibility findings for review. Import does not silently normalize Article frontmatter.
- Welcome page links keep readable colors on hover in both light and dark mode.

## Existing behavior to retain or explain

The importer creates a setup commit, preserves an existing hand-written index and manifest, and later keeps unknown frontmatter fields when Articles are edited. Import reports a declared `okf_version` other than 0.2 and leaves the original index intact. Later YAML serialization may change comments or formatting in an edited Article.
