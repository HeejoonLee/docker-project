"""Data passed between the web app, workflows and activities."""

import re
from typing import Literal

from pydantic import BaseModel, field_validator

from stonepedia.bundle import BundleSettings, Template

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

ChangeKind = Literal["create", "update", "retire"]
SourceKind = Literal["text", "file", "link", "request"]
Decision = Literal["pending", "accepted", "discarded"]
ProposalState = Literal["generating", "awaiting_review", "committing", "done", "discarded", "failed"]


class BundleSpec(BaseModel):
    """Machine-level facts about a Bundle, kept in its BundleWorkflow.

    Knowledge-level settings (language, ids, Template) live in the repo under .stonepedia/.
    """

    slug: str
    name: str
    language: str = "ko"  # initial value for a new Bundle's settings
    id_prefix: str = ""  # initial value for a new Bundle's settings
    clone_url: str = ""  # set when the Bundle was created from an existing repo
    remote_url: str = ""  # where commits are pushed; empty = local only
    branch: str = "main"
    root: str = "."  # the Bundle's folder inside the repo

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("slug must be lowercase letters, digits and dashes")
        return v

    @field_validator("root")
    @classmethod
    def _root(cls, v: str) -> str:
        v = v.strip().strip("/") or "."
        if v.startswith("/") or ".." in v.split("/"):
            raise ValueError("root must be a folder inside the repository")
        return v


class SourceInput(BaseModel):
    """What the submitter gave us. Files are staged under <data>/uploads/<proposal id>/ by the web app."""

    kind: SourceKind
    text: str = ""  # text and request
    url: str = ""  # link
    filename: str = ""  # file: the uploaded file's original name


class SourceInfo(BaseModel):
    """A prepared Source folder (see stonepedia.sources)."""

    id: str
    kind: SourceKind
    title: str
    original: str  # file name of the original inside the folder
    filename: str = ""
    url: str = ""
    media: str = ""
    pages: int | None = None
    text_chars: int = 0
    submitted_by: str = ""
    submitted_at: str = ""
    sha256: str = ""
    warnings: list[str] = []
    preview: str = ""  # start of the extracted text, for the review screen


class PushState(BaseModel):
    state: Literal["off", "ok", "pending", "failed"] = "off"
    error: str = ""
    retry: bool = True  # whether the workflow retries by itself
    at: str = ""


class BundleStatus(BaseModel):
    spec: BundleSpec
    push: PushState
    last_commit: str | None = None


class BundleConfigUpdate(BaseModel):
    """A change from the Bundle settings page. None = leave as is."""

    editor: str
    settings: "BundleSettings | None" = None
    template: "Template | None" = None
    remote_url: str | None = None
    branch: str | None = None


class BundleInit(BaseModel):
    head: str
    branch: str


class BundleRun(BaseModel):
    spec: BundleSpec
    initialized: bool = False
    push: PushState = PushState()


class ChangeVersion(BaseModel):
    """An earlier version of an Article change, kept when it is revised or edited."""

    content: str
    replaced_by: Literal["revise", "edit", "feedback"]
    note: str = ""  # reviewer feedback that led to the replacement
    by: str = ""
    at: str = ""


class ArticleChange(BaseModel):
    id: str
    path: str
    kind: ChangeKind
    base_blob: str | None  # blob at the time the change was produced; None for create
    base_content: str | None = None
    content: str
    title: str = ""
    decision: Decision = "pending"
    stale: bool = False
    edited_by: str | None = None
    history: list[ChangeVersion] = []


AgentMode = Literal["propose", "revise", "feedback"]


class AgentJob(BaseModel):
    """One run of the proposing agent for a Proposal."""

    proposal_id: str
    bundle: str
    root: str = "."
    mode: AgentMode
    title: str
    source: SourceInfo
    submitted_by: str
    request_targets: list[str] = []  # Articles a Request is aimed at
    feedback: str = ""
    feedback_by: str = ""
    # Current content of this Proposal's non-discarded changes, placed into the workspace first.
    carried: list[ArticleChange] = []
    # revise: the paths to revise. feedback: paths of accepted changes that must stay as they are.
    targets: list[str] = []
    locked: list[str] = []
    attempt_key: str = ""


class AgentOutcome(BaseModel):
    changes: list[ArticleChange]
    summary: str = ""
    agent: str = ""
    cost_usd: float | None = None


class AgentCheck(BaseModel):
    ok: bool
    message: str
    agent: str
    seconds: float


class ProposalInput(BaseModel):
    proposal_id: str
    bundle: str
    title: str
    source: SourceInput
    submitted_by: str
    targets: list[str] = []  # Requests: Articles the Request is aimed at


class ProposalView(BaseModel):
    id: str
    bundle: str
    title: str
    submitted_by: str
    source_kind: SourceKind
    source: SourceInfo | None = None
    targets: list[str] = []
    state: ProposalState
    changes: list[ArticleChange] = []
    error: str | None = None
    commit: str | None = None
    reviewer: str | None = None
    summary: str = ""  # the agent's own account of its latest run
    cost_usd: float = 0.0
    runs: int = 0


class CommitRequest(BaseModel):
    proposal_id: str
    title: str
    reviewer: str
    source_id: str | None = None
    changes: list[ArticleChange]  # accepted changes only


class CommitResult(BaseModel):
    commit: str | None = None
    stale_ids: list[str] = []
