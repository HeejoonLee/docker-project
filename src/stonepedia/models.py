"""Data passed between the web app, workflows and activities."""

import re
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from stonepedia.bundle import BundleSettings, Template

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

ChangeKind = Literal["create", "update", "retire"]
# "code" only appears on Proposals started before a Proposal could carry several Sources.
SourceKind = Literal["text", "file", "link", "request", "code", "audit"]
MAX_SOURCES = 20
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
    reference_dir: str = ""  # path beneath the worker's read-only /references mount
    reference_excludes: list[str] = [".git", ".env*", "node_modules", ".venv", "dist", "build"]

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

    @field_validator("reference_dir")
    @classmethod
    def _reference_dir(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("/") or ".." in v.split("/"):
            raise ValueError("reference_dir must stay inside the mounted reference root")
        return v.rstrip("/")


class SourceInput(BaseModel):
    """One item the submitter gave us. Files are staged under <data>/uploads/<proposal id>/<n>/ by the web app."""

    kind: SourceKind
    text: str = ""  # text, request and audit
    url: str = ""  # link
    filename: str = ""  # file: the uploaded file's original name
    title: str = ""  # optional, chosen by the submitter


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
    reference_dir: str | None = None
    reference_excludes: list[str] | None = None


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
    reference_dir: str = ""  # resolved worker path, absent when Bundle has no reference
    reference_excludes: list[str] = []
    mode: AgentMode
    title: str
    sources: list[SourceInfo] = []
    request: SourceInfo | None = None  # the Request (kind request), or the audit instructions (kind audit)
    use_reference: bool = False  # the Reference directory's code is material to document
    submitted_by: str
    request_targets: list[str] = []  # Articles a Request is aimed at
    note: str = ""
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
    sources: list[SourceInput] = []  # texts, files and links, in submission order
    request: str = ""  # the Request text, or the audit instructions
    audit: bool = False
    use_reference: bool = False  # document code from the Bundle's Reference directory
    submitted_by: str
    targets: list[str] = []  # Articles the Request is aimed at
    note: str = ""  # extra context for the agent (e.g. why maintenance opened this Proposal)
    origin: Literal["person", "maintenance"] = "person"
    # Proposals started before 0.4 carry exactly one Source here; it is read into the fields above.
    source: SourceInput | None = None

    @model_validator(mode="after")
    def _from_single_source(self) -> "ProposalInput":
        src = self.source
        if src is None or self.sources or self.request:
            return self
        if src.kind in ("text", "file", "link"):
            self.sources = [src]
        else:
            self.request = src.text
            self.audit = src.kind == "audit"
            self.use_reference = src.kind == "code"
        return self


class PreparedSources(BaseModel):
    sources: list[SourceInfo] = []
    request: SourceInfo | None = None


class ProposalView(BaseModel):
    id: str
    bundle: str
    title: str
    submitted_by: str
    sources: list[SourceInfo] = []
    request: SourceInfo | None = None
    request_text: str = ""
    use_reference: bool = False
    targets: list[str] = []
    note: str = ""
    origin: Literal["person", "maintenance"] = "person"
    state: ProposalState
    changes: list[ArticleChange] = []
    error: str | None = None
    commit: str | None = None
    reviewer: str | None = None
    summary: str = ""  # the agent's own account of its latest run
    cost_usd: float = 0.0
    runs: int = 0
    reference_used: bool = False
    code_stale_paths: list[str] = []


class CommitRequest(BaseModel):
    proposal_id: str
    title: str
    reviewer: str
    source_ids: list[str] = []  # Sources (and the Request) cited by the accepted changes
    request_text: str = ""
    request_by: str = ""
    source_id: str | None = None  # before 0.4
    changes: list[ArticleChange]  # accepted changes only


class CommitResult(BaseModel):
    commit: str | None = None
    stale_ids: list[str] = []
    stale_code_paths: list[str] = []


class Finding(BaseModel):
    severity: Literal["error", "warning"]
    kind: str
    path: str
    message: str


MaintenanceCheck = Literal["integrity", "links"]


class MaintenanceInput(BaseModel):
    bundle: str
    check: MaintenanceCheck
    requested_by: str = "schedule"


class ChangedLink(BaseModel):
    source_id: str
    url: str
    title: str
    cited_by: list[str]
    error: str = ""


class MaintenanceReport(BaseModel):
    bundle: str
    check: MaintenanceCheck
    requested_by: str
    findings: list[Finding] = []
    proposals: list[str] = []  # Proposals opened by this run
    summary: str = ""
