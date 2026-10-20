"""Web API and static UI: `uvicorn stonepedia.web:app`.

The web app never writes to a Bundle. It starts and talks to workflows through the
Temporal client, and reads Bundle repos only to display them.
"""

import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from temporalio.client import Client, WorkflowFailureError, WorkflowQueryFailedError, WorkflowUpdateFailedError
from temporalio.common import SearchAttributePair, TypedSearchAttributes, WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.api.workflowservice.v1 import GetSystemInfoRequest
from temporalio.service import RPCError

from stonepedia import appconfig, bundle, config, git, schedules, search
from stonepedia.bundle import BundleSettings, Template
from stonepedia.models import (
    AgentCheck,
    BundleConfigUpdate,
    BundleRun,
    BundleSpec,
    BundleStatus,
    MaintenanceCheck,
    MaintenanceInput,
    MaintenanceReport,
    ProposalInput,
    ProposalView,
    PushState,
    SourceInput,
)
from stonepedia.sources import SUPPORTED_EXTS
from stonepedia.temporal import connect
from stonepedia.workflows import AgentCheckWorkflow, BundleWorkflow, MaintenanceWorkflow, ProposalWorkflow

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
    id: str
    title: str
    type: str
    status: str


class BundleDetail(BaseModel):
    slug: str
    name: str
    settings: BundleSettings
    root: str
    remote_url: str  # with any embedded token hidden
    branch: str
    clone_url: str
    push: PushState
    head: str | None
    articles: list[ArticleSummary]


class BundleSettingsBody(BaseModel):
    editor: str
    settings: BundleSettings
    remote_url: str
    branch: str


class TemplateBody(BaseModel):
    editor: str
    template: Template


@app.get("/api/config")
async def get_config(request: Request) -> dict:
    settings = _settings(request)
    ui = settings.temporal_ui_url or f"{request.url.scheme}://{request.url.hostname}:{settings.temporal_ui_port}"
    return {"temporal_ui_url": ui.rstrip("/"), "namespace": settings.namespace}


@app.get("/api/health")
async def health(request: Request) -> dict:
    """For Docker health checks: the web app is up and can reach Temporal."""
    try:
        await _client(request).workflow_service.get_system_info(GetSystemInfoRequest(), timeout=timedelta(seconds=3))
    except Exception as err:  # any failure means unhealthy
        raise HTTPException(503, f"Temporal unreachable: {err}")
    return {"ok": True}


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
    spec.clone_url = spec.clone_url.strip()
    spec.remote_url = spec.remote_url.strip()
    try:
        handle = await _client(request).start_workflow(
            BundleWorkflow.run,
            BundleRun(spec=spec),
            id=f"bundle-{spec.slug}",
            task_queue=config.TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            memo={"name": spec.name, "language": spec.language},
        )
    except WorkflowAlreadyStartedError:
        raise HTTPException(409, f"A Bundle named '{spec.slug}' already exists.")
    try:
        await handle.execute_update(BundleWorkflow.wait_ready)
    except (WorkflowUpdateFailedError, RPCError):
        try:
            await handle.result()
        except WorkflowFailureError as err:
            raise HTTPException(422, f"Could not create the Bundle: {_root_cause(err)}")
        raise
    return BundleSummary(slug=spec.slug, name=spec.name, language=spec.language, created_at=None)


async def _bundle_status(request: Request, slug: str) -> BundleStatus:
    try:
        return await _client(request).get_workflow_handle(f"bundle-{slug}").query(BundleWorkflow.status)
    except (RPCError, WorkflowQueryFailedError):
        raise HTTPException(404, "No such Bundle.")


@app.get("/api/bundles/{slug}")
async def get_bundle(slug: str, request: Request) -> BundleDetail:
    status = await _bundle_status(request, slug)
    spec = status.spec
    repo = _settings(request).bundles_dir / slug
    root = repo / spec.root
    settings = bundle.load_settings(root)
    articles = [
        ArticleSummary(
            path=rel,
            id=str(bundle.get_field(meta, settings.id_field) or ""),
            title=str(meta.get("title", rel)),
            type=str(meta.get("type", "")),
            status=str(meta.get("status", "")),
        )
        for rel, meta in bundle.articles(root)
    ]
    return BundleDetail(
        slug=slug,
        name=settings.name,
        settings=settings,
        root=spec.root,
        remote_url=git.redact(spec.remote_url),
        branch=spec.branch,
        clone_url=git.redact(spec.clone_url),
        push=status.push,
        head=git.head(repo) if (repo / ".git").exists() else None,
        articles=articles,
    )


@app.put("/api/bundles/{slug}/settings")
async def put_bundle_settings(slug: str, body: BundleSettingsBody, request: Request) -> BundleDetail:
    status = await _bundle_status(request, slug)
    remote = body.remote_url.strip()
    if remote == git.redact(status.spec.remote_url):
        remote = status.spec.remote_url  # unchanged (the UI only ever sees the redacted form)
    update = BundleConfigUpdate(
        editor=body.editor.strip() or "anonymous",
        settings=body.settings,
        remote_url=remote if remote != status.spec.remote_url else None,
        branch=body.branch.strip() if body.branch.strip() != status.spec.branch else None,
    )
    await _update(_client(request).get_workflow_handle(f"bundle-{slug}").execute_update(BundleWorkflow.save_config, update))
    return await get_bundle(slug, request)


@app.get("/api/bundles/{slug}/template")
async def get_template(slug: str, request: Request, inferred: bool = False) -> Template:
    status = await _bundle_status(request, slug)
    root = _settings(request).bundles_dir / slug / status.spec.root
    return bundle.infer_template(root) if inferred else bundle.load_template(root)


@app.put("/api/bundles/{slug}/template")
async def put_template(slug: str, body: TemplateBody, request: Request) -> Template:
    await _bundle_status(request, slug)
    update = BundleConfigUpdate(editor=body.editor.strip() or "anonymous", template=body.template)
    await _update(_client(request).get_workflow_handle(f"bundle-{slug}").execute_update(BundleWorkflow.save_config, update))
    return body.template


@app.post("/api/bundles/{slug}/push")
async def retry_push(slug: str, request: Request) -> PushState:
    await _bundle_status(request, slug)
    status = await _update(_client(request).get_workflow_handle(f"bundle-{slug}").execute_update(BundleWorkflow.retry_push))
    return status.push


@app.get("/api/bundles/{slug}/articles/{path:path}")
async def get_article(slug: str, path: str, request: Request) -> dict:
    status = await _bundle_status(request, slug)
    root = (_settings(request).bundles_dir / slug / status.spec.root).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.suffix != ".md":
        raise HTTPException(404, "No such Article.")
    return {"path": path, "content": target.read_text()}


def _root_cause(err: BaseException) -> str:
    while err.__cause__ is not None:
        err = err.__cause__
    return getattr(err, "message", None) or str(err)


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
    proposal_id = _new_proposal_id()

    filename = ""
    if kind == "file":
        assert file is not None and file.filename
        filename = Path(file.filename).name
        if Path(filename).suffix.lower() not in SUPPORTED_EXTS:
            raise HTTPException(422, f"Unsupported file type. Supported: {', '.join(sorted(SUPPORTED_EXTS))}")
        await _save_upload(file, settings.uploads_dir / proposal_id / filename,
                           appconfig.load(settings.config_dir).max_source_mb * 2**20)

    first_line = text.strip().splitlines()[0][:80] if text.strip() else ""
    fallback = filename or first_line  # links: the page title, filled in once the page is fetched
    inp = ProposalInput(
        proposal_id=proposal_id,
        bundle=bundle,
        title=title or fallback,
        source=SourceInput(kind=kind, text=text, url=url.strip(), filename=filename),
        submitted_by=submitted_by.strip() or "anonymous",
        targets=[t.strip() for t in targets.splitlines() if t.strip()] if kind == "request" else [],
    )
    return await _start_proposal(request, inp)


def _new_proposal_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)


async def _start_proposal(request: Request, inp: ProposalInput) -> ProposalSummary:
    await _client(request).start_workflow(
        ProposalWorkflow.run,
        inp,
        id=f"proposal-{inp.proposal_id}",
        task_queue=config.TASK_QUEUE,
        memo={"title": inp.title or inp.source.url or inp.proposal_id, "submitted_by": inp.submitted_by, "kind": inp.source.kind},
        search_attributes=TypedSearchAttributes(
            [SearchAttributePair(search.BUNDLE, inp.bundle), SearchAttributePair(search.PROPOSAL_STATE, "generating")]
        ),
    )
    return ProposalSummary(
        id=inp.proposal_id,
        bundle=inp.bundle,
        title=inp.title or inp.source.url or inp.proposal_id,
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


# ---------- Maintenance ----------

AUDIT_INSTRUCTIONS = """Review all Articles in this Bundle and propose fixes for:
1. Duplicate or overlapping Articles: merge them into one and retire the others.
2. Contradictions between Articles: fix them when the Bundle's own content settles the question;
   otherwise record the conflict as an open question in each affected Article.
3. Broken or outdated links and cross-references between Articles.
4. Articles that do not follow the Template (type, required fields, structure).
Only make changes you can justify from what the Bundle already contains."""


class ReportSummary(BaseModel):
    workflow_id: str
    run_id: str
    check: str
    requested_by: str
    started_at: str | None
    status: str
    summary: str


class MaintenanceOverview(BaseModel):
    timezone: str
    schedules: dict[str, schedules.ScheduleConfig]
    reports: list[ReportSummary]


class RunBody(BaseModel):
    requested_by: str


class AuditBody(BaseModel):
    requested_by: str
    focus: str = ""


@app.get("/api/maintenance/{slug}")
async def get_maintenance(slug: str, request: Request) -> MaintenanceOverview:
    await _bundle_status(request, slug)
    client = _client(request)
    reports = []
    query = f"WorkflowType='MaintenanceWorkflow' AND Bundle='{_quote(slug)}'"
    async for wf in client.list_workflows(query, limit=20):
        memo = await wf.memo()
        reports.append(ReportSummary(
            workflow_id=wf.id,
            run_id=wf.run_id,
            check=memo.get("check", ""),
            requested_by=memo.get("requested_by", "schedule"),
            started_at=_ts(wf.start_time),
            status=wf.status.name.lower() if wf.status else "",
            summary=memo.get("summary", ""),
        ))
    reports.sort(key=lambda r: r.started_at or "", reverse=True)
    return MaintenanceOverview(
        timezone=_settings(request).timezone,
        schedules={c: await schedules.get(client, slug, c) for c in ("integrity", "links")},
        reports=reports,
    )


@app.put("/api/maintenance/{slug}/schedules/{check}")
async def put_schedule(slug: str, check: MaintenanceCheck, body: schedules.ScheduleConfig, request: Request) -> schedules.ScheduleConfig:
    await _bundle_status(request, slug)
    return await schedules.put(_client(request), _settings(request), slug, check, body)


@app.post("/api/maintenance/{slug}/run/{check}")
async def run_maintenance(slug: str, check: MaintenanceCheck, body: RunBody, request: Request) -> ReportSummary:
    await _bundle_status(request, slug)
    who = body.requested_by.strip() or "anonymous"
    handle = await _client(request).start_workflow(
        MaintenanceWorkflow.run,
        MaintenanceInput(bundle=slug, check=check, requested_by=who),
        id=f"maintenance-{slug}-{check}-{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(2)}",
        task_queue=config.TASK_QUEUE,
        memo={"check": check, "requested_by": who},
        search_attributes=TypedSearchAttributes([SearchAttributePair(search.BUNDLE, slug)]),
    )
    return ReportSummary(workflow_id=handle.id, run_id=handle.result_run_id or "", check=check, requested_by=who,
                         started_at=_ts(datetime.now(UTC)), status="running", summary="")


@app.get("/api/maintenance/reports/{workflow_id}/{run_id}")
async def get_report(workflow_id: str, run_id: str, request: Request) -> MaintenanceReport | None:
    handle = _client(request).get_workflow_handle_for(MaintenanceWorkflow.run, workflow_id, run_id=run_id)
    try:
        desc = await handle.describe()
        if desc.status is None or desc.status.name != "COMPLETED":
            return None
        return await handle.result()
    except (RPCError, WorkflowFailureError):
        raise HTTPException(404, "No such report.")


@app.post("/api/bundles/{slug}/audit", status_code=201)
async def start_audit(slug: str, body: AuditBody, request: Request) -> ProposalSummary:
    await _bundle_status(request, slug)
    text = AUDIT_INSTRUCTIONS + (f"\n\nFocus: {body.focus.strip()}" if body.focus.strip() else "")
    return await _start_proposal(request, ProposalInput(
        proposal_id=_new_proposal_id(),
        bundle=slug,
        title="AI audit" + (f": {body.focus.strip()[:60]}" if body.focus.strip() else ""),
        source=SourceInput(kind="audit", text=text),
        submitted_by=body.requested_by.strip() or "anonymous",
    ))


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
