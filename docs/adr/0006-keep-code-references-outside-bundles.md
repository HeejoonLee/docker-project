---
status: accepted
---

# Keep source-code references outside Bundles

A Bundle may use a server-mounted, read-only Reference directory as evidence for Proposals, including Proposals started directly from a code-focused instruction. Stonepedia keeps the code outside the Bundle and records cited file paths and content hashes in Articles, plus a git commit when available. This avoids importing a large, changing source tree into the knowledge repository, while making the evidence for accepted claims identifiable and allowing Stonepedia to flag stale proposals when cited code changes. The deployment must provide the directory mount, and reviewers must explicitly refresh proposals based on changed cited files. Bundle-specific exclusion patterns guide the agent's search but do not restrict access to the mounted directory; operators must mount only directories whose contents the agent may read.
