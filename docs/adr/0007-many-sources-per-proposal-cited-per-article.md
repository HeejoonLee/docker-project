---
status: accepted
---

# Many Sources per Proposal, each cited per Article by the agent

A Proposal may bring any number of Sources (texts, files, links in any mix), alongside an optional Request and the Reference directory. Knowledge is usually gathered from several places at once, and forcing one Source per Proposal split related material into separate, conflicting Proposals. Each Source stays one atomic item in its own folder, `sources/<proposal id>-<n>/`, so per-item citations, the integrity check and link refresh keep working unchanged, and older `sources/<proposal id>/` folders stay valid. Instead of the system stamping every Source on every changed Article, the agent declares per Article which Sources it relied on (`source_refs`, like `code_refs`); the system validates them, writes the `sources` frontmatter, and rejects a created or updated Article that cites no Source, Request or code file. Only Sources cited by an accepted change are committed to the Bundle; the Request text always goes into the commit message.

## Considered Options

- **One composite Source with several parts**: one folder per Proposal. Rejected: citations could not name the part used, and link refresh works per URL.
- **Cite every Source on every changed Article**: no agent cooperation needed. Rejected: Articles would claim evidence they never used.
- **Skip unreadable Sources and continue**: Rejected: Articles would silently miss material the Reviewer believes was used. A Proposal fails before the agent runs, naming the Source.
