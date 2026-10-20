"""Data passed between the web app, workflows and activities."""

import re
from typing import Literal

from pydantic import BaseModel, field_validator

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

ChangeKind = Literal["create", "update", "retire"]
Decision = Literal["pending", "accepted", "discarded"]
ProposalState = Literal["generating", "awaiting_review", "committing", "done", "discarded", "failed"]


class BundleSpec(BaseModel):
    slug: str
    name: str
    language: str = "ko"
    id_prefix: str = ""

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("slug must be lowercase letters, digits and dashes")
        return v


class BundleRun(BaseModel):
    spec: BundleSpec
    initialized: bool = False


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


class AgentTask(BaseModel):
    proposal_id: str
    bundle: str
    title: str
    text: str
    submitted_by: str


class ProposalInput(BaseModel):
    proposal_id: str
    bundle: str
    title: str
    text: str
    submitted_by: str


class ProposalView(BaseModel):
    id: str
    bundle: str
    title: str
    text: str
    submitted_by: str
    state: ProposalState
    changes: list[ArticleChange] = []
    error: str | None = None
    commit: str | None = None
    reviewer: str | None = None


class CommitRequest(BaseModel):
    proposal_id: str
    title: str
    reviewer: str
    changes: list[ArticleChange]  # accepted changes only


class CommitResult(BaseModel):
    commit: str | None = None
    stale_ids: list[str] = []
