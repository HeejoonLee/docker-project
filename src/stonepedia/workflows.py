"""Temporal workflows. A Bundle and a Proposal each live as one workflow."""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from stonepedia import frontmatter, search
    from stonepedia.activities import Activities
    from stonepedia.models import (
        AgentCheck,
        AgentJob,
        AgentMode,
        AgentOutcome,
        ArticleChange,
        BundleRun,
        BundleSpec,
        ChangeVersion,
        CommitRequest,
        CommitResult,
        Decision,
        ProposalInput,
        ProposalState,
        ProposalView,
    )

_SHORT = timedelta(minutes=2)
_AGENT_LIMIT = timedelta(hours=10)  # the activity enforces the configured, shorter limit
_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class BundleWorkflow:
    """Owns one Bundle repo and serializes every git write to it."""

    def __init__(self) -> None:
        self._spec: BundleSpec | None = None
        self._ready = False
        self._lock = asyncio.Lock()
        self._last_commit: str | None = None

    @workflow.run
    async def run(self, inp: BundleRun) -> None:
        spec = self._spec = inp.spec
        if not inp.initialized:
            self._last_commit = await workflow.execute_activity_method(
                Activities.init_bundle, spec, start_to_close_timeout=_SHORT, retry_policy=_RETRY
            )
        self._ready = True
        await workflow.wait_condition(
            lambda: workflow.info().is_continue_as_new_suggested() and workflow.all_handlers_finished()
        )
        workflow.continue_as_new(BundleRun(spec=spec, initialized=True))

    @workflow.update
    async def commit(self, req: CommitRequest) -> CommitResult:
        await workflow.wait_condition(lambda: self._ready)
        assert self._spec is not None
        async with self._lock:
            result = await workflow.execute_activity_method(
                Activities.commit_changes,
                args=[self._spec.slug, req],
                start_to_close_timeout=_SHORT,
                retry_policy=_RETRY,
            )
        if result.commit:
            self._last_commit = result.commit
        return result

    @workflow.update
    async def wait_ready(self) -> str | None:
        """Returns once the Bundle repo exists, with its latest commit."""
        await workflow.wait_condition(lambda: self._ready)
        return self._last_commit

    @workflow.query
    def info(self) -> BundleSpec | None:
        return self._spec


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
            source_kind=inp.source.kind,
            targets=inp.targets,
            state="generating",
        )
        self._submitted_by: str | None = None
        self._jobs: list[AgentJob] = []

    @workflow.run
    async def run(self, inp: ProposalInput) -> ProposalView:
        try:
            self._view.source = await workflow.execute_activity_method(
                Activities.prepare_source, inp, start_to_close_timeout=timedelta(minutes=10), retry_policy=_RETRY
            )
        except ActivityError as err:
            self._view.error = f"Could not read the Source: {_cause(err)}"
            self._set_state("failed")
            return self._view
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

    # ---------- Agent runs ----------

    def _job(self, mode: AgentMode, feedback: str = "", targets: list[str] | None = None) -> AgentJob:
        return AgentJob(
            proposal_id=self._inp.proposal_id,
            bundle=self._inp.bundle,
            mode=mode,
            title=self._inp.title,
            source=self._view.source,
            submitted_by=self._inp.submitted_by,
            request_targets=self._inp.targets,
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
                        source_id=self._view.source.id if self._view.source else None,
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
        self._view.commit = result.commit
        self._view.reviewer = reviewer
        self._view.error = None
        self._set_state("done")
        return True

    # ---------- Review actions ----------

    @workflow.query
    def view(self) -> ProposalView:
        return self._view

    @workflow.update
    def decide(self, change_id: str, decision: Decision) -> ProposalView:
        self._change(change_id).decision = decision
        return self._view

    @decide.validator
    def _validate_decide(self, change_id: str, decision: Decision) -> None:
        self._require_reviewable()
        change = self._find(change_id)
        if decision == "accepted" and change.stale:
            raise ApplicationError("This change is stale; revise or edit it before accepting.")

    @workflow.update
    def revise(self, change_id: str, feedback: str, reviewer: str) -> ProposalView:
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
    def feedback(self, text: str, reviewer: str) -> ProposalView:
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
        return self._view

    @edit.validator
    def _validate_edit(self, change_id: str, content: str, editor: str) -> None:
        self._require_reviewable()
        if self._find(change_id).decision != "pending":
            raise ApplicationError("Undo the decision on this change before editing it.")
        if not content.strip():
            raise ApplicationError("The Article cannot be empty; discard the change instead.")

    @workflow.update
    def submit(self, reviewer: str) -> ProposalView:
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
