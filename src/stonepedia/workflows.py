"""Temporal workflows. A Bundle and a Proposal each live as one workflow."""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, SearchAttributePair, TypedSearchAttributes
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from stonepedia import config, frontmatter, references, search
    from stonepedia.activities import Activities, cited_ids
    from stonepedia.models import (
        AgentCheck,
        AgentJob,
        AgentMode,
        AgentOutcome,
        ArticleChange,
        BundleConfigUpdate,
        BundleRun,
        BundleSpec,
        BundleStatus,
        ChangeVersion,
        CommitRequest,
        CommitResult,
        Decision,
        Finding,
        MaintenanceInput,
        MaintenanceReport,
        PreparedSources,
        ProposalInput,
        ProposalState,
        ProposalView,
        PushState,
        SourceInput,
    )

_SHORT = timedelta(minutes=2)
_AGENT_LIMIT = timedelta(hours=10)  # the activity enforces the configured, shorter limit
_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class BundleWorkflow:
    """Owns one Bundle repo: serializes every git write to it and pushes to its remote."""

    def __init__(self) -> None:
        self._spec: BundleSpec | None = None
        self._ready = False
        self._lock = asyncio.Lock()
        self._last_commit: str | None = None
        self._push = PushState()
        self._push_wanted = False

    @workflow.run
    async def run(self, inp: BundleRun) -> None:
        self._spec = inp.spec
        self._push = inp.push
        if not inp.initialized:
            init = await workflow.execute_activity_method(
                Activities.init_bundle, inp.spec, start_to_close_timeout=timedelta(minutes=15), retry_policy=_RETRY
            )
            self._spec.branch = init.branch
            self._last_commit = init.head
            if self._spec.remote_url or self._spec.clone_url:
                self._spec.remote_url = self._spec.remote_url or self._spec.clone_url
                self._push_wanted = True  # publish the first commit (Bundle setup)
                self._push = PushState(state="pending")
        self._ready = True

        while not self._should_restart():
            try:
                await workflow.wait_condition(
                    lambda: self._push_wanted or self._should_restart(), timeout=self._retry_after()
                )
            except asyncio.TimeoutError:
                self._push_wanted = True  # automatic retry after a failed push
            if self._push_wanted and not self._should_restart():
                self._push_wanted = False
                await self._push_now()
        workflow.continue_as_new(BundleRun(spec=self._spec, initialized=True, push=self._push))

    def _should_restart(self) -> bool:
        return workflow.info().is_continue_as_new_suggested() and workflow.all_handlers_finished()

    def _retry_after(self) -> timedelta | None:
        if self._push.state == "failed" and self._push.retry:
            return timedelta(minutes=10)
        return None

    async def _push_now(self) -> None:
        assert self._spec is not None
        if not self._spec.remote_url:
            self._push = PushState(state="off")
            return
        async with self._lock:
            try:
                await workflow.execute_activity_method(
                    Activities.push_bundle,
                    self._spec,
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5)),
                )
                self._push = PushState(state="ok", at=_now())
            except ActivityError as err:
                cause = err.cause
                conflict = isinstance(cause, ApplicationError) and cause.type == "Conflict"
                self._push = PushState(state="failed", error=_cause(err), retry=not conflict, at=_now())

    async def _sync_first(self) -> None:
        """Before writing, pull in remote commits so stale checks see them. Offline is not fatal."""
        assert self._spec is not None
        if not self._spec.remote_url:
            return
        try:
            await workflow.execute_activity_method(
                Activities.sync_bundle,
                self._spec,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError as err:
            self._push = PushState(state="failed", error=_cause(err), retry=self._push.retry, at=_now())

    def _after_write(self, commit: str | None) -> None:
        if commit:
            self._last_commit = commit
            if self._spec and self._spec.remote_url:
                self._push_wanted = True
                if self._push.state != "failed":
                    self._push = PushState(state="pending")

    @workflow.update
    async def commit(self, req: CommitRequest) -> CommitResult:
        await workflow.wait_condition(lambda: self._ready)
        assert self._spec is not None
        async with self._lock:
            await self._sync_first()
            result = await workflow.execute_activity_method(
                Activities.commit_changes,
                args=[self._spec, req],
                start_to_close_timeout=_SHORT,
                retry_policy=_RETRY,
            )
        self._after_write(result.commit)
        return result

    @workflow.update
    async def save_config(self, req: BundleConfigUpdate) -> BundleStatus:
        """Change Bundle settings, Template and/or remote. Settings and Template are committed."""
        await workflow.wait_condition(lambda: self._ready)
        assert self._spec is not None
        async with self._lock:
            if req.reference_dir is not None:
                await workflow.execute_activity_method(
                    Activities.validate_reference, req.reference_dir, start_to_close_timeout=_SHORT, retry_policy=_RETRY
                )
                self._spec.reference_dir = req.reference_dir
            if req.reference_excludes is not None:
                self._spec.reference_excludes = req.reference_excludes
            if req.remote_url is not None or req.branch is not None:
                self._spec.remote_url = req.remote_url if req.remote_url is not None else self._spec.remote_url
                self._spec.branch = req.branch or self._spec.branch
                await workflow.execute_activity_method(
                    Activities.set_remote, self._spec, start_to_close_timeout=_SHORT, retry_policy=_RETRY
                )
                self._push = PushState(state="pending" if self._spec.remote_url else "off")
                self._push_wanted = bool(self._spec.remote_url)
            if req.settings is not None or req.template is not None:
                await self._sync_first()
                commit = await workflow.execute_activity_method(
                    Activities.save_bundle_config,
                    args=[self._spec, req.settings, req.template, req.editor],
                    start_to_close_timeout=_SHORT,
                    retry_policy=_RETRY,
                )
                self._after_write(commit)
            if req.settings is not None:
                self._spec.name = req.settings.name
                workflow.upsert_memo({"name": req.settings.name, "language": req.settings.language})
        return self.status()

    @workflow.update
    def retry_push(self) -> BundleStatus:
        self._push_wanted = True
        self._push = PushState(state="pending")
        return self.status()

    @workflow.update(unfinished_policy=workflow.HandlerUnfinishedPolicy.ABANDON)
    async def wait_ready(self) -> str | None:
        """Returns once the Bundle repo exists, with its latest commit. Abandoned if creation fails."""
        await workflow.wait_condition(lambda: self._ready)
        return self._last_commit

    @workflow.query
    def info(self) -> BundleSpec | None:
        return self._spec

    @workflow.query
    def status(self) -> BundleStatus:
        assert self._spec is not None
        return BundleStatus(spec=self._spec, push=self._push, last_commit=self._last_commit)


def _now() -> str:
    return workflow.now().isoformat(timespec="seconds")


@workflow.defn
class ProposalWorkflow:
    """One Proposal: run the agent, wait for review (revising as asked), commit the accepted changes."""

    @workflow.init
    def __init__(self, inp: ProposalInput) -> None:
        self._inp = inp
        self._view = ProposalView(
            id=inp.proposal_id,
            bundle=inp.bundle,
            title=inp.title,
            submitted_by=inp.submitted_by,
            request_text=inp.request,
            use_reference=inp.use_reference,
            targets=inp.targets,
            note=inp.note,
            origin=inp.origin,
            state="generating",
        )
        self._submitted_by: str | None = None
        self._jobs: list[AgentJob] = []

    @workflow.run
    async def run(self, inp: ProposalInput) -> ProposalView:
        try:
            prepared = await self._prepare(inp)
        except ActivityError as err:
            self._view.error = f"Could not read a Source: {_cause(err)}"
            self._set_state("failed")
            return self._view
        self._view.sources, self._view.request = prepared.sources, prepared.request
        if not self._view.title:  # e.g. only links: use the first page title
            first = (prepared.sources or [prepared.request])[0]
            self._view.title = first.title if first else inp.proposal_id
            workflow.upsert_memo({"title": self._view.title})
        await self._run_agent(self._job("propose"))
        if not self._view.changes:
            self._set_state("failed")
            await workflow.wait_condition(workflow.all_handlers_finished)
            return self._view

        while True:
            await workflow.wait_condition(lambda: self._submitted_by is not None or bool(self._jobs))
            if self._jobs:
                await self._run_agent(self._jobs.pop(0))
                continue
            if await self._commit():
                break

        await workflow.wait_condition(workflow.all_handlers_finished)
        return self._view

    async def _prepare(self, inp: ProposalInput) -> PreparedSources:
        if workflow.patched("many-sources"):
            return await workflow.execute_activity_method(
                Activities.prepare_sources, inp, start_to_close_timeout=timedelta(minutes=30), retry_policy=_RETRY
            )
        # Started before a Proposal could carry several Sources: one folder named after the Proposal.
        info = await workflow.execute_activity_method(
            Activities.prepare_source, inp, start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY
        )
        if info.kind in ("request", "code", "audit"):
            return PreparedSources(request=info)
        return PreparedSources(sources=[info])

    # ---------- Agent runs ----------

    def _job(self, mode: AgentMode, feedback: str = "", targets: list[str] | None = None) -> AgentJob:
        return AgentJob(
            proposal_id=self._inp.proposal_id,
            bundle=self._inp.bundle,
            mode=mode,
            title=self._view.title,
            sources=self._view.sources,
            request=self._view.request,
            use_reference=self._inp.use_reference,
            submitted_by=self._inp.submitted_by,
            request_targets=self._inp.targets,
            note=self._inp.note,
            feedback=feedback,
            targets=targets or [],
        )

    async def _run_agent(self, job: AgentJob) -> None:
        job.carried = [c for c in self._view.changes if c.decision != "discarded"]
        job.locked = [c.path for c in self._view.changes if c.decision == "accepted"]
        job.attempt_key = str(self._view.runs)
        self._set_state("generating")
        self._view.error = None
        try:
            outcome = await workflow.execute_activity_method(
                Activities.run_agent,
                job,
                start_to_close_timeout=_AGENT_LIMIT,
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except ActivityError as err:
            self._view.error = f"The agent failed: {_cause(err)}"
            self._set_state("awaiting_review" if self._view.changes else "failed")
            return
        self._view.runs += 1
        self._view.cost_usd += outcome.cost_usd or 0.0
        self._view.summary = outcome.summary
        self._merge(job, outcome)
        if not self._view.changes and job.mode == "propose":
            self._view.error = "The agent proposed no Article changes."
            self._set_state("failed")
            return
        self._set_state("awaiting_review")

    def _merge(self, job: AgentJob, outcome: AgentOutcome) -> None:
        if job.mode == "propose":
            self._view.changes = outcome.changes
            self._view.reference_used = any(references.citations_from_content(c.content) for c in self._view.changes)
            self._view.code_stale_paths = []
            return
        now = workflow.now().isoformat(timespec="seconds")
        new_by_path = {c.path: c for c in outcome.changes}
        if job.mode == "revise":
            for path in job.targets:
                old = next(c for c in self._view.changes if c.path == path)
                new = new_by_path.get(path)
                if new is None:
                    self._view.error = f"The agent left {path} identical to the knowledge base."
                    continue
                if new.content != old.content or old.stale:
                    _replace(old, new, ChangeVersion(
                        content=old.content, replaced_by="revise", note=job.feedback, by=job.feedback_by, at=now
                    ))
            self._view.reference_used = any(references.citations_from_content(c.content) for c in self._view.changes)
            self._view.code_stale_paths = []
            return
        # Whole-Proposal feedback: accepted changes stay, pending ones may change or be withdrawn.
        merged: list[ArticleChange] = []
        old_by_path = {c.path: c for c in self._view.changes}
        for old in self._view.changes:
            if old.decision == "accepted" or (old.decision == "discarded" and old.path not in new_by_path):
                merged.append(old)
        for path, new in new_by_path.items():
            if path in job.locked:
                continue
            old = old_by_path.get(path)
            if old is None:
                merged.append(new)
                continue
            if new.content != old.content or old.decision == "discarded" or old.stale:
                _replace(old, new, ChangeVersion(
                    content=old.content, replaced_by="feedback", note=job.feedback, by=job.feedback_by, at=now
                ))
            merged.append(old)
        order = {c.path: i for i, c in enumerate(self._view.changes)}
        self._view.changes = sorted(merged, key=lambda c: order.get(c.path, len(order)))
        self._view.reference_used = any(references.citations_from_content(c.content) for c in self._view.changes)
        self._view.code_stale_paths = []

    async def _check_code(self) -> list[str]:
        if not self._view.reference_used:
            self._view.code_stale_paths = []
            return []
        contents = [c.content for c in self._view.changes if c.decision != "discarded"]
        self._view.code_stale_paths = await workflow.execute_activity_method(
            Activities.check_reference, args=[self._view.bundle, contents],
            start_to_close_timeout=_SHORT, retry_policy=_RETRY,
        )
        return self._view.code_stale_paths

    # ---------- Commit ----------

    async def _commit(self) -> bool:
        """Commit accepted changes. Returns True when the Proposal is finished."""
        reviewer = self._submitted_by
        assert reviewer is not None
        accepted = [c for c in self._view.changes if c.decision == "accepted"]
        if not accepted:
            self._view.reviewer = reviewer
            self._set_state("discarded")
            return True
        if await self._check_code():
            self._view.error = "Cited code changed. Refresh the Proposal before submitting."
            self._submitted_by = None
            self._set_state("awaiting_review")
            return False
        self._set_state("committing")
        try:
            result = await workflow.execute_activity_method(
                Activities.commit_via_bundle,
                args=[
                    self._view.bundle,
                    CommitRequest(
                        proposal_id=self._view.id,
                        title=self._view.title,
                        reviewer=reviewer,
                        changes=accepted,
                        source_ids=self._cited_sources(accepted),
                        request_text=self._view.request_text,
                        request_by=self._inp.submitted_by,
                    ),
                ],
                start_to_close_timeout=_SHORT,
                retry_policy=_RETRY,
            )
        except ActivityError as err:
            self._view.error = f"Commit failed: {_cause(err)}"
            self._submitted_by = None
            self._set_state("awaiting_review")
            return False
        if result.stale_ids:
            for change in self._view.changes:
                if change.id in result.stale_ids:
                    change.stale = True
                    change.decision = "pending"
            self._view.error = "Some accepted changes are stale: their Articles changed since they were proposed."
            self._submitted_by = None
            self._set_state("awaiting_review")
            return False
        if result.stale_code_paths:
            self._view.code_stale_paths = result.stale_code_paths
            for change in self._view.changes:
                if any(c.get("path") in result.stale_code_paths for c in references.citations_from_content(change.content)):
                    change.decision = "pending"
            self._view.error = "Cited code changed. Refresh the Proposal before submitting."
            self._submitted_by = None
            self._set_state("awaiting_review")
            return False
        self._view.commit = result.commit
        self._view.reviewer = reviewer
        self._view.error = None
        self._set_state("done")
        return True

    def _cited_sources(self, changes: list[ArticleChange]) -> list[str]:
        items = self._view.sources + ([self._view.request] if self._view.request else [])
        ids = [i.id for i in items if i.kind != "audit"]
        cited = {sid for c in changes for sid in cited_ids(c.content, ids)}
        return [i for i in ids if i in cited]

    # ---------- Review actions ----------

    @workflow.query
    def view(self) -> ProposalView:
        return self._view

    @workflow.update
    async def check_code(self) -> ProposalView:
        if self._view.state == "awaiting_review":
            await self._check_code()
        return self._view

    @workflow.update
    async def decide(self, change_id: str, decision: Decision) -> ProposalView:
        if decision == "accepted" and await self._check_code():
            raise ApplicationError("Cited code changed. Refresh the Proposal before accepting.")
        self._change(change_id).decision = decision
        return self._view

    @decide.validator
    def _validate_decide(self, change_id: str, decision: Decision) -> None:
        self._require_reviewable()
        change = self._find(change_id)
        if decision == "accepted" and change.stale:
            raise ApplicationError("This change is stale; revise or edit it before accepting.")

    @workflow.update
    async def revise(self, change_id: str, feedback: str, reviewer: str) -> ProposalView:
        if await self._check_code():
            raise ApplicationError("Cited code changed. Refresh the Proposal before revising.")
        change = self._change(change_id)
        job = self._job("revise", feedback=feedback, targets=[change.path])
        job.feedback_by = reviewer
        self._jobs.append(job)
        self._set_state("generating")
        return self._view

    @revise.validator
    def _validate_revise(self, change_id: str, feedback: str, reviewer: str) -> None:
        self._require_reviewable()
        if self._find(change_id).decision != "pending":
            raise ApplicationError("Undo the decision on this change before revising it.")

    @workflow.update
    async def feedback(self, text: str, reviewer: str) -> ProposalView:
        if await self._check_code():
            raise ApplicationError("Cited code changed. Refresh the Proposal before revising.")
        job = self._job("feedback", feedback=text)
        job.feedback_by = reviewer
        self._jobs.append(job)
        self._set_state("generating")
        return self._view

    @feedback.validator
    def _validate_feedback(self, text: str, reviewer: str) -> None:
        self._require_reviewable()
        if not text.strip():
            raise ApplicationError("Write the feedback first.")

    @workflow.update
    async def refresh_code(self, reviewer: str) -> ProposalView:
        self._require_reviewable()
        stale = await self._check_code()
        if not stale:
            return self._view
        for change in self._view.changes:
            if any(c.get("path") in stale for c in references.citations_from_content(change.content)):
                change.decision = "pending"
        job = self._job("feedback", feedback="Refresh the proposed Articles against the current code. Re-read and cite current files.")
        job.feedback_by = reviewer
        self._jobs.append(job)
        self._set_state("generating")
        return self._view

    @workflow.update
    async def edit(self, change_id: str, content: str, editor: str) -> ProposalView:
        change = self._change(change_id)
        if change.stale:
            fresh = await workflow.execute_activity_method(
                Activities.refresh_base,
                args=[self._view.bundle, change.path],
                start_to_close_timeout=_SHORT,
                retry_policy=_RETRY,
            )
            change.base_blob, change.base_content, change.kind = fresh.base_blob, fresh.base_content, fresh.kind
            change.stale = False
        change.history.append(ChangeVersion(
            content=change.content, replaced_by="edit", by=editor, at=workflow.now().isoformat(timespec="seconds")
        ))
        change.content = content
        change.edited_by = editor
        meta, _ = frontmatter.split(content)
        change.title = str(meta.get("title", change.title))
        self._view.reference_used = any(references.citations_from_content(c.content) for c in self._view.changes)
        return self._view

    @edit.validator
    def _validate_edit(self, change_id: str, content: str, editor: str) -> None:
        self._require_reviewable()
        if self._find(change_id).decision != "pending":
            raise ApplicationError("Undo the decision on this change before editing it.")
        if not content.strip():
            raise ApplicationError("The Article cannot be empty; discard the change instead.")

    @workflow.update
    async def submit(self, reviewer: str) -> ProposalView:
        if any(c.decision == "accepted" for c in self._view.changes) and await self._check_code():
            raise ApplicationError("Cited code changed. Refresh the Proposal before submitting.")
        self._submitted_by = reviewer
        return self._view

    @submit.validator
    def _validate_submit(self, reviewer: str) -> None:
        self._require_reviewable()
        if not reviewer.strip():
            raise ApplicationError("A reviewer name is required.")
        if any(c.decision == "pending" for c in self._view.changes):
            raise ApplicationError("Decide on every change before submitting.")

    # ---------- Helpers ----------

    def _find(self, change_id: str) -> ArticleChange:
        change = next((c for c in self._view.changes if c.id == change_id), None)
        if change is None:
            raise ApplicationError(f"No change {change_id}")
        return change

    def _change(self, change_id: str) -> ArticleChange:
        return self._find(change_id)

    def _require_reviewable(self) -> None:
        if self._view.state != "awaiting_review" or self._submitted_by is not None or self._jobs:
            raise ApplicationError(f"Proposal is {self._view.state}, not awaiting review.")

    def _set_state(self, state: ProposalState) -> None:
        self._view.state = state
        workflow.upsert_search_attributes([search.PROPOSAL_STATE.value_set(state)])


def _replace(old: ArticleChange, new: ArticleChange, previous: ChangeVersion) -> None:
    old.history.append(previous)
    old.content = new.content
    old.base_blob = new.base_blob
    old.base_content = new.base_content
    old.kind = new.kind
    old.title = new.title
    old.stale = False
    old.decision = "pending"
    old.edited_by = None


def _cause(err: BaseException) -> str:
    while err.__cause__ is not None:
        err = err.__cause__
    return str(err)


@workflow.defn
class AgentCheckWorkflow:
    """Runs the configured agent once with a trivial prompt (Settings page "Test" button)."""

    @workflow.run
    async def run(self) -> AgentCheck:
        return await workflow.execute_activity_method(
            Activities.check_agent,
            start_to_close_timeout=timedelta(minutes=4),
            heartbeat_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )


@workflow.defn
class MaintenanceWorkflow:
    """One Maintenance check of one Bundle. Produces a report, and Proposals for changed links."""

    @workflow.run
    async def run(self, inp: MaintenanceInput) -> MaintenanceReport:
        report = MaintenanceReport(bundle=inp.bundle, check=inp.check, requested_by=inp.requested_by)
        workflow.upsert_memo({"check": inp.check, "requested_by": inp.requested_by})
        if inp.check == "integrity":
            report.findings = await workflow.execute_activity_method(
                Activities.integrity_check, inp.bundle, start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY
            )
            errors = sum(f.severity == "error" for f in report.findings)
            warnings = len(report.findings) - errors
            report.summary = f"{errors} errors, {warnings} warnings" if report.findings else "No problems found"
        else:
            changed = await workflow.execute_activity_method(
                Activities.find_changed_links,
                inp.bundle,
                start_to_close_timeout=timedelta(minutes=60),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=_RETRY,
            )
            for link in changed:
                if link.error:
                    report.findings.append(Finding(
                        severity="warning", kind="link_unreachable", path=f"sources/{link.source_id}",
                        message=f"{link.url}: {link.error}",
                    ))
                    continue
                report.proposals.append(await self._open_refresh_proposal(inp, link))
            report.summary = f"{len(report.proposals)} changed, {len(report.findings)} unreachable"
        workflow.upsert_memo({"summary": report.summary, "check": inp.check})
        return report

    async def _open_refresh_proposal(self, inp: MaintenanceInput, link) -> str:
        pid = workflow.now().strftime("%Y%m%d-%H%M%S-") + workflow.uuid4().hex[:4]
        cited = ", ".join(f"`{p}`" for p in link.cited_by)
        proposal = ProposalInput(
            proposal_id=pid,
            bundle=inp.bundle,
            title=f"Updated: {link.title}",
            sources=[SourceInput(kind="link", url=link.url)],
            submitted_by="Stonepedia maintenance",
            note=(
                f"This page changed since it was captured as Source `sources/{link.source_id}/` "
                f"(compare with its text.md). Update the Articles that cite it ({cited}) to match the current "
                "page. Change only what the page changed; if nothing relevant changed, make no edits."
            ),
            origin="maintenance",
        )
        await workflow.start_child_workflow(
            ProposalWorkflow.run,
            proposal,
            id=f"proposal-{pid}",
            task_queue=config.TASK_QUEUE,
            parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            memo={"title": proposal.title, "submitted_by": proposal.submitted_by, "kind": "link"},
            search_attributes=TypedSearchAttributes([
                SearchAttributePair(search.BUNDLE, inp.bundle),
                SearchAttributePair(search.PROPOSAL_STATE, "generating"),
            ]),
        )
        return pid
