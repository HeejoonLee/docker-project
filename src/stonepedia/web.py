"""Web API and static UI: `uvicorn stonepedia.web:app`.

The web app never writes to a Bundle. It starts and talks to workflows through the
Temporal client, and reads Bundle repos only to display them.
"""

import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from temporalio.client import Client, WorkflowUpdateFailedError
from temporalio.common import SearchAttributePair, TypedSearchAttributes, WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError

from stonepedia import appconfig, config, frontmatter, git, search
from stonepedia.models import AgentCheck, BundleRun, BundleSpec, ProposalInput, ProposalView, SourceInput
from stonepedia.sources import SUPPORTED_EXTS
from stonepedia.temporal import connect
from stonepedia.workflows import AgentCheckWorkflow, BundleWorkflow, ProposalWorkflow

STATIC_DIR = Path(__file__).resolve().parents[2] / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = config.load()
    app.state.client = await connect(app.state.settings)
    yield


app = FastAPI(title="Stonepedia", lifespan=lifespan)


def _client(request: Request) -> Client:
    return request.app.state.client


def _settings(request: Request) -> config.Settings:
    return request.app.state.settings


def _ts(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat(timespec="seconds") if dt else None


# ---------- Bundles ----------


class BundleSummary(BaseModel):
    slug: str
    name: str
    language: str
    created_at: str | None


class ArticleSummary(BaseModel):
    path: str
    title: str
    type: str
    status: str


class BundleDetail(BundleSummary):
    head: str | None
    articles: list[ArticleSummary]


@app.get("/api/config")
async def get_config(request: Request) -> dict:
    return {"temporal_ui_url": _settings(request).temporal_ui_url, "namespace": _settings(request).namespace}


@app.get("/api/bundles")
async def list_bundles(request: Request) -> list[BundleSummary]:
    out = []
    query = "WorkflowType='BundleWorkflow' AND ExecutionStatus='Running'"
    async for wf in _client(request).list_workflows(query):
        memo = await wf.memo()
        out.append(
            BundleSummary(
                slug=wf.id.removeprefix("bundle-"),
                name=memo.get("name", wf.id),
                language=memo.get("language", ""),
                created_at=_ts(wf.start_time),
            )
        )
    return sorted(out, key=lambda b: b.name.lower())


@app.post("/api/bundles", status_code=201)
async def create_bundle(spec: BundleSpec, request: Request) -> BundleSummary:
    if (_settings(request).bundles_dir / spec.slug).exists():
        raise HTTPException(409, f"A Bundle folder named '{spec.slug}' already exists.")
    try:
        handle = await _client(request).start_workflow(
            BundleWorkflow.run,
            BundleRun(spec=spec),
            id=f"bundle-{spec.slug}",
            task_queue=config.TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            memo={"name": spec.name, "language": spec.language},
        )
    except WorkflowAlreadyStartedError:
        raise HTTPException(409, f"A Bundle named '{spec.slug}' already exists.")
    await _update(handle.execute_update(BundleWorkflow.wait_ready))
    return BundleSummary(slug=spec.slug, name=spec.name, language=spec.language, created_at=None)


@app.get("/api/bundles/{slug}")
async def get_bundle(slug: str, request: Request) -> BundleDetail:
    try:
        spec = await _client(request).get_workflow_handle(f"bundle-{slug}").query(BundleWorkflow.info)
    except RPCError:
        raise HTTPException(404, "No such Bundle.")
    if spec is None:
        raise HTTPException(404, "No such Bundle.")
    repo = _settings(request).bundles_dir / slug
    head = git.head(repo) if (repo / ".git").exists() else None
    articles = []
    if head:
        for path in sorted(repo.rglob("*.md")):
            rel = path.relative_to(repo).as_posix()
            if rel in ("index.md", "README.md") or rel.startswith((".stonepedia/", "sources/", ".git/")):
                continue
            meta, _ = frontmatter.split(path.read_text())
            articles.append(
                ArticleSummary(
                    path=rel,
                    title=str(meta.get("title", rel)),
                    type=str(meta.get("type", "")),
                    status=str(meta.get("status", "")),
                )
            )
    return BundleDetail(
        slug=slug, name=spec.name, language=spec.language, created_at=None, head=head, articles=articles
    )


@app.get("/api/bundles/{slug}/articles/{path:path}")
async def get_article(slug: str, path: str, request: Request) -> dict:
    repo = (_settings(request).bundles_dir / slug).resolve()
    target = (repo / path).resolve()
    if not target.is_relative_to(repo) or not target.is_file() or target.suffix != ".md":
        raise HTTPException(404, "No such Article.")
    return {"path": path, "content": target.read_text()}


# ---------- Proposals ----------


class ProposalSummary(BaseModel):
    id: str
    bundle: str
    title: str
    submitted_by: str
    state: str
    created_at: str | None


class DecisionBody(BaseModel):
    decision: Literal["pending", "accepted", "discarded"]


class SubmitBody(BaseModel):
    reviewer: str


class ReviseBody(BaseModel):
    feedback: str = ""
    reviewer: str


class FeedbackBody(BaseModel):
    text: str
    reviewer: str


class EditBody(BaseModel):
    content: str
    editor: str


def _proposal_handle(request: Request, proposal_id: str):
    return _client(request).get_workflow_handle(f"proposal-{proposal_id}")


@app.get("/api/proposals")
async def list_proposals(request: Request, bundle: str | None = None, state: str | None = None) -> list[ProposalSummary]:
    query = "WorkflowType='ProposalWorkflow'"
    if bundle:
        query += f" AND Bundle='{_quote(bundle)}'"
    if state:
        query += f" AND ProposalState='{_quote(state)}'"
    out = []
    async for wf in _client(request).list_workflows(query, limit=500):
        memo = await wf.memo()
        sa = wf.typed_search_attributes
        out.append(
            ProposalSummary(
                id=wf.id.removeprefix("proposal-"),
                bundle=sa.get(search.BUNDLE) or "",
                title=memo.get("title", ""),
                submitted_by=memo.get("submitted_by", ""),
                state=sa.get(search.PROPOSAL_STATE) or "",
                created_at=_ts(wf.start_time),
            )
        )
    return sorted(out, key=lambda p: p.created_at or "", reverse=True)


@app.post("/api/proposals", status_code=201)
async def create_proposal(
    request: Request,
    bundle: str = Form(...),
    kind: Literal["text", "file", "link", "request"] = Form(...),
    submitted_by: str = Form(""),
    title: str = Form(""),
    text: str = Form(""),
    url: str = Form(""),
    targets: str = Form(""),  # Requests: newline-separated Article paths
    file: UploadFile | None = File(None),
) -> ProposalSummary:
    settings = _settings(request)
    if not (settings.bundles_dir / bundle / ".git").exists():
        raise HTTPException(404, "No such Bundle.")
    title = title.strip()
    if kind in ("text", "request") and not text.strip():
        raise HTTPException(422, "Text is required.")
    if kind == "link" and not url.strip().startswith(("http://", "https://")):
        raise HTTPException(422, "Enter a link starting with http:// or https://")
    if kind == "file" and (file is None or not file.filename):
        raise HTTPException(422, "Choose a file.")
    proposal_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)

    filename = ""
    if kind == "file":
        assert file is not None and file.filename
        filename = Path(file.filename).name
        if Path(filename).suffix.lower() not in SUPPORTED_EXTS:
            raise HTTPException(422, f"Unsupported file type. Supported: {', '.join(sorted(SUPPORTED_EXTS))}")
        await _save_upload(file, settings.uploads_dir / proposal_id / filename,
                           appconfig.load(settings.config_dir).max_source_mb * 2**20)

    first_line = text.strip().splitlines()[0][:80] if text.strip() else ""
    fallback = filename or url.strip() or first_line
    inp = ProposalInput(
        proposal_id=proposal_id,
        bundle=bundle,
        title=title or fallback or proposal_id,
        source=SourceInput(kind=kind, text=text, url=url.strip(), filename=filename),
        submitted_by=submitted_by.strip() or "anonymous",
        targets=[t.strip() for t in targets.splitlines() if t.strip()] if kind == "request" else [],
    )
    await _client(request).start_workflow(
        ProposalWorkflow.run,
        inp,
        id=f"proposal-{proposal_id}",
        task_queue=config.TASK_QUEUE,
        memo={"title": inp.title, "submitted_by": inp.submitted_by, "kind": kind},
        search_attributes=TypedSearchAttributes(
            [SearchAttributePair(search.BUNDLE, inp.bundle), SearchAttributePair(search.PROPOSAL_STATE, "generating")]
        ),
    )
    return ProposalSummary(
        id=proposal_id,
        bundle=inp.bundle,
        title=inp.title,
        submitted_by=inp.submitted_by,
        state="generating",
        created_at=_ts(datetime.now(UTC)),
    )


async def _save_upload(file: UploadFile, dest: Path, max_bytes: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"The file is larger than {max_bytes // 2**20} MB (change the limit in Settings).")
            out.write(chunk)


@app.get("/api/proposals/{proposal_id}/source/{name}")
async def get_source_file(proposal_id: str, name: str, request: Request) -> FileResponse:
    folder = (_settings(request).sources_dir / proposal_id).resolve()
    target = (folder / name).resolve()
    if not target.is_relative_to(folder) or not target.is_file():
        raise HTTPException(404, "No such Source file.")
    media = "text/plain; charset=utf-8" if target.suffix in (".md", ".yaml", ".txt", ".html") else None
    return FileResponse(target, media_type=media, content_disposition_type="inline")


@app.get("/api/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, request: Request) -> ProposalView:
    try:
        return await _proposal_handle(request, proposal_id).query(ProposalWorkflow.view)
    except RPCError:
        raise HTTPException(404, "No such Proposal.")


@app.post("/api/proposals/{proposal_id}/changes/{change_id}/decision")
async def decide(proposal_id: str, change_id: str, body: DecisionBody, request: Request) -> ProposalView:
    return await _update(_proposal_handle(request, proposal_id).execute_update(
        ProposalWorkflow.decide, args=[change_id, body.decision]
    ))


@app.post("/api/proposals/{proposal_id}/submit")
async def submit(proposal_id: str, body: SubmitBody, request: Request) -> ProposalView:
    return await _update(_proposal_handle(request, proposal_id).execute_update(
        ProposalWorkflow.submit, body.reviewer.strip()
    ))


@app.post("/api/proposals/{proposal_id}/changes/{change_id}/revise")
async def revise(proposal_id: str, change_id: str, body: ReviseBody, request: Request) -> ProposalView:
    return await _update(_proposal_handle(request, proposal_id).execute_update(
        ProposalWorkflow.revise, args=[change_id, body.feedback, body.reviewer.strip()]
    ))


@app.post("/api/proposals/{proposal_id}/changes/{change_id}/edit")
async def edit(proposal_id: str, change_id: str, body: EditBody, request: Request) -> ProposalView:
    return await _update(_proposal_handle(request, proposal_id).execute_update(
        ProposalWorkflow.edit, args=[change_id, body.content, body.editor.strip()]
    ))


@app.post("/api/proposals/{proposal_id}/feedback")
async def feedback(proposal_id: str, body: FeedbackBody, request: Request) -> ProposalView:
    return await _update(_proposal_handle(request, proposal_id).execute_update(
        ProposalWorkflow.feedback, args=[body.text, body.reviewer.strip()]
    ))


async def _update(coro):
    try:
        return await coro
    except WorkflowUpdateFailedError as err:
        raise HTTPException(409, str(err.cause.message if err.cause else err))
    except RPCError as err:
        raise HTTPException(409, err.message)


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


# ---------- Settings ----------


class SettingsBody(BaseModel):
    app: appconfig.AppConfig
    claude_settings: str


@app.get("/api/settings")
async def get_settings(request: Request) -> SettingsBody:
    cfg_dir = _settings(request).config_dir
    return SettingsBody(app=appconfig.load(cfg_dir), claude_settings=appconfig.load_claude_settings(cfg_dir))


@app.put("/api/settings")
async def put_settings(body: SettingsBody, request: Request) -> SettingsBody:
    cfg_dir = _settings(request).config_dir
    try:
        appconfig.save_claude_settings(cfg_dir, body.claude_settings)
    except ValueError as err:
        raise HTTPException(422, f"Claude settings: {err}")
    appconfig.save(cfg_dir, body.app)
    return body


@app.post("/api/settings/test")
async def test_agent(request: Request) -> AgentCheck:
    return await _client(request).execute_workflow(
        AgentCheckWorkflow.run,
        id=f"agent-check-{secrets.token_hex(4)}",
        task_queue=config.TASK_QUEUE,
    )


# ---------- Static UI ----------

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file() and candidate.resolve().is_relative_to(STATIC_DIR):
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
