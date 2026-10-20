"""Temporal workflows. A Bundle and a Proposal each live as one workflow."""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from stonepedia import search
    from stonepedia.activities import Activities
    from stonepedia.models import (
        AgentTask,
        BundleRun,
        BundleSpec,
        CommitRequest,
        CommitResult,
        Decision,
        ProposalInput,
        ProposalState,
        ProposalView,
    )

_SHORT = timedelta(minutes=2)
_AGENT = timedelta(minutes=60)
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
    """One Proposal: generate Article changes, wait for review, commit the accepted ones."""

    @workflow.init
    def __init__(self, inp: ProposalInput) -> None:
        self._view = ProposalView(
            id=inp.proposal_id,
            bundle=inp.bundle,
            title=inp.title,
            text=inp.text,
            submitted_by=inp.submitted_by,
            state="generating",
        )
        self._submitted_by: str | None = None

    @workflow.run
    async def run(self, inp: ProposalInput) -> ProposalView:
        task = AgentTask(
            proposal_id=inp.proposal_id,
            bundle=inp.bundle,
            title=inp.title,
            text=inp.text,
            submitted_by=inp.submitted_by,
        )
        try:
            self._view.changes = await workflow.execute_activity_method(
                Activities.generate_changes, task, start_to_close_timeout=_AGENT, retry_policy=_RETRY
            )
        except ActivityError as err:
            return self._fail(f"Generating changes failed: {_cause(err)}")
        if not self._view.changes:
            return self._fail("The agent proposed no Article changes.")
        self._set_state("awaiting_review")

        while True:
            await workflow.wait_condition(lambda: self._submitted_by is not None)
            reviewer = self._submitted_by
            assert reviewer is not None
            accepted = [c for c in self._view.changes if c.decision == "accepted"]
            if not accepted:
                self._view.reviewer = reviewer
                self._set_state("discarded")
                break
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
                        ),
                    ],
                    start_to_close_timeout=_SHORT,
                    retry_policy=_RETRY,
                )
            except ActivityError as err:
                self._view.error = f"Commit failed: {_cause(err)}"
                self._submitted_by = None
                self._set_state("awaiting_review")
                continue
            if result.stale_ids:
                for change in self._view.changes:
                    if change.id in result.stale_ids:
                        change.stale = True
                        change.decision = "pending"
                self._view.error = "Some accepted changes are stale: their Articles changed since they were proposed."
                self._submitted_by = None
                self._set_state("awaiting_review")
                continue
            self._view.commit = result.commit
            self._view.reviewer = reviewer
            self._view.error = None
            self._set_state("done")
            break

        await workflow.wait_condition(workflow.all_handlers_finished)
        return self._view

    @workflow.query
    def view(self) -> ProposalView:
        return self._view

    @workflow.update
    def decide(self, change_id: str, decision: Decision) -> ProposalView:
        change = next(c for c in self._view.changes if c.id == change_id)
        change.decision = decision
        return self._view

    @decide.validator
    def _validate_decide(self, change_id: str, decision: Decision) -> None:
        self._require_reviewable()
        change = next((c for c in self._view.changes if c.id == change_id), None)
        if change is None:
            raise ApplicationError(f"No change {change_id}")
        if decision == "accepted" and change.stale:
            raise ApplicationError("This change is stale; revise or edit it before accepting.")

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

    def _require_reviewable(self) -> None:
        if self._view.state != "awaiting_review" or self._submitted_by is not None:
            raise ApplicationError(f"Proposal is {self._view.state}, not awaiting review.")

    def _set_state(self, state: ProposalState) -> None:
        self._view.state = state
        workflow.upsert_search_attributes([search.PROPOSAL_STATE.value_set(state)])

    def _fail(self, message: str) -> ProposalView:
        self._view.error = message
        self._set_state("failed")
        return self._view


def _cause(err: BaseException) -> str:
    while err.__cause__ is not None:
        err = err.__cause__
    return str(err)
