# Stonepedia

Stonepedia turns incoming documents into reviewed, git-versioned knowledge for AI agents. Every change to the knowledge base is proposed, reviewed by a human, and only then committed.

## Knowledge

**Knowledge base**:
All Bundles managed by one Stonepedia deployment.
_Avoid_: KB repo, wiki, corpus

**Bundle**:
One project's accepted Articles and Sources, kept as its own git repository with its own remote (e.g. GitLab) and its own Template.
_Avoid_: Collection, space, project folder

**Template**:
A Bundle's editable Article contract: type vocabulary, frontmatter fields, sections per type, and writing guidance. New Bundles copy the global default.
_Avoid_: Profile, schema

**Article**:
A single OKF v0.2 Markdown file in a Bundle, with frontmatter and body.
_Avoid_: Knowledge document, knowledge unit, page

**Source**:
Anything ingested as evidence for Articles: a link, a PDF, an image of a handwritten note. Its original and extracted text are kept so that Articles can cite it.
_Avoid_: Input, upload, reference document

## Review

**Proposal**:
A changeset against one Bundle, started from a Source, a Request, or a Maintenance check, and awaiting human review. It never changes the knowledge base by itself.
_Avoid_: Draft, suggestion, PR

**Request**:
A Reviewer's typed instruction to change knowledge without a new Source. It is kept as an attributed statement that Articles can cite.
_Avoid_: Prompt, ticket

**Stale**:
The state of an Article change whose underlying Article has changed since the change was produced. It cannot be accepted until it is revised or edited.

**Article change**:
One element of a Proposal: creating or updating a single Article. Each is decided on independently.
_Avoid_: Diff, patch, item

**Accept**:
The decision that commits an Article change into the knowledge base. All Article changes accepted together in one Proposal form a single commit.

**Revise**:
The decision that asks the AI for a new version of an Article change, optionally guided by the reviewer's feedback. Earlier versions are kept.
_Avoid_: Re-propose, regenerate

**Edit**:
The decision in which the reviewer rewrites an Article change by hand before accepting it.

**Discard**:
The decision that drops an Article change, optionally with a reason.
_Avoid_: Reject, delete

**Reviewer**:
The person deciding on Article changes, identified only by a self-chosen display name.
_Avoid_: User, approver

## Maintenance

**Maintenance check**:
A scheduled inspection of the knowledge base (integrity, Source refresh, or AI audit) whose output is a report or a Proposal, never a direct change.
_Avoid_: Cron job, lint
