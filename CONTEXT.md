# Stonepedia

Stonepedia turns incoming documents into reviewed, git-versioned knowledge for AI agents. Every change to the knowledge base is proposed, reviewed by a human, and only then committed.

## Knowledge

**Knowledge base**:
All Bundles managed by one Stonepedia deployment.
_Avoid_: KB repo, wiki, corpus

**Bundle**:
One project's accepted Articles and Sources, kept in its own git repository (the whole repository or one folder of it) with its own remote (e.g. GitLab) and its own Template.
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

**Reference directory**:
A persistent, read-only source-code directory associated with a Bundle that the proposing agent can consult when working on its Articles or when starting a Proposal from code. Its code stays outside the Bundle.
_Avoid_: Uploaded Source, Bundle root

**Code citation**:
An Article's reference to a file in its Bundle's Reference directory, identified by its relative path and content hash, plus the code's git commit when available.
_Avoid_: Source archive

## Review

**Proposal**:
A changeset against one Bundle, started from a Source, a Request, or a Maintenance check, and awaiting human review. It never changes the knowledge base by itself.
_Avoid_: Draft, suggestion, PR

**Request**:
A Reviewer's typed instruction to change knowledge without a new Source. It is kept as an attributed statement that Articles can cite.
_Avoid_: Prompt, ticket

**Stale**:
The state of an Article change whose underlying Article has changed, or of a Proposal whose cited code files have changed, since the change was produced. A stale code reference must be explicitly refreshed before its Proposal can be accepted or revised.

**Article change**:
One element of a Proposal: creating, updating or retiring a single Article. Each is decided on independently.
_Avoid_: Diff, patch, item

**Retire**:
An Article change that marks an Article obsolete. The file stays in the Bundle with status `retired`, so links and history keep working.
_Avoid_: Delete, archive

**Accept**:
The decision that commits an Article change into the knowledge base. All Article changes accepted together in one Proposal form a single commit.

**Revise**:
The decision that asks the AI for a new version of an Article change, optionally guided by the reviewer's feedback. Earlier versions are kept.
_Avoid_: Re-propose, regenerate

**Proposal feedback**:
A Reviewer's comment on a whole Proposal that sends it back to the AI. Undecided Article changes may be reworked, added or withdrawn; accepted ones stay as they are.
_Avoid_: Comment, re-plan

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
A scheduled or on-demand inspection of one Bundle (integrity or Source refresh) whose output is a report or Proposals, never a direct change.
_Avoid_: Cron job, lint

**AI audit**:
A Reviewer-started Proposal in which the AI reviews a Bundle's Articles for problems, optionally with a focus. It is not a Maintenance check and cannot be scheduled.
_Avoid_: Maintenance audit
