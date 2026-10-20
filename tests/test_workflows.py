import pytest
from temporalio.client import WorkflowUpdateFailedError
from temporalio.common import SearchAttributePair, TypedSearchAttributes

from stonepedia import config, frontmatter, git, search
from stonepedia.models import BundleRun, BundleSpec, ProposalInput
from stonepedia.workflows import BundleWorkflow, ProposalWorkflow

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def start_bundle(env, slug):
    handle = await env.client.start_workflow(
        BundleWorkflow.run, BundleRun(spec=BundleSpec(slug=slug, name=slug)), id=f"bundle-{slug}", task_queue=config.TASK_QUEUE
    )
    return handle


async def start_proposal(env, bundle, pid, title="Boot sequence", text="Board boots from LU 1."):
    inp = ProposalInput(proposal_id=pid, bundle=bundle, title=title, text=text, submitted_by="kim")
    return await env.client.start_workflow(
        ProposalWorkflow.run,
        inp,
        id=f"proposal-{pid}",
        task_queue=config.TASK_QUEUE,
        search_attributes=TypedSearchAttributes(
            [SearchAttributePair(search.BUNDLE, bundle), SearchAttributePair(search.PROPOSAL_STATE, "generating")]
        ),
    )


async def wait_state(handle, state):
    for _ in range(100):
        view = await handle.query(ProposalWorkflow.view)
        if view.state == state:
            return view
        await __import__("asyncio").sleep(0.1)
    raise AssertionError(f"state stayed {view.state}, wanted {state}")


async def test_accept_commits_article(env, worker, settings, uid):
    await start_bundle(env, f"b{uid}")
    p = await start_proposal(env, f"b{uid}", f"p{uid}")
    view = await wait_state(p, "awaiting_review")
    [change] = view.changes
    assert change.kind == "create" and change.path == "notes/boot-sequence.md"

    with pytest.raises(WorkflowUpdateFailedError):
        await p.execute_update(ProposalWorkflow.submit, "lee")  # undecided change

    await p.execute_update(ProposalWorkflow.decide, args=[change.id, "accepted"])
    await p.execute_update(ProposalWorkflow.submit, "lee")
    result = await p.result()
    assert result.state == "done" and result.reviewer == "lee"

    repo = settings.bundles_dir / f"b{uid}"
    meta, body = frontmatter.split((repo / change.path).read_text())
    assert meta["status"] == "accepted" and meta["review"]["reviewer"] == "lee"
    assert "LU 1" in body
    log = git.git(repo, "log", "-1", "--format=%an|%B")
    assert log.startswith("lee|Boot sequence") and f"Proposal: p{uid}" in log


async def test_second_change_to_same_article_goes_stale(env, worker, settings, uid):
    await start_bundle(env, f"b{uid}")
    a = await start_proposal(env, f"b{uid}", f"a{uid}")
    b = await start_proposal(env, f"b{uid}", f"b{uid}")
    va = await wait_state(a, "awaiting_review")
    vb = await wait_state(b, "awaiting_review")

    await a.execute_update(ProposalWorkflow.decide, args=[va.changes[0].id, "accepted"])
    await a.execute_update(ProposalWorkflow.submit, "lee")
    assert (await a.result()).state == "done"

    await b.execute_update(ProposalWorkflow.decide, args=[vb.changes[0].id, "accepted"])
    await b.execute_update(ProposalWorkflow.submit, "lee")
    view = await wait_state(b, "awaiting_review")
    assert view.changes[0].stale and view.changes[0].decision == "pending"
    with pytest.raises(WorkflowUpdateFailedError):
        await b.execute_update(ProposalWorkflow.decide, args=[vb.changes[0].id, "accepted"])

    await b.execute_update(ProposalWorkflow.decide, args=[vb.changes[0].id, "discarded"])
    await b.execute_update(ProposalWorkflow.submit, "lee")
    assert (await b.result()).state == "discarded"


async def test_unknown_bundle_fails_cleanly(env, worker, uid):
    p = await start_proposal(env, f"missing{uid}", f"x{uid}")
    result = await p.result()
    assert result.state == "failed" and "Generating changes failed" in result.error
