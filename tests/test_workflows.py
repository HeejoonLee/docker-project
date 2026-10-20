import pytest
from temporalio.client import WorkflowUpdateFailedError
from helpers import start_bundle, start_proposal, wait_state
from stonepedia import frontmatter, git
from stonepedia.workflows import ProposalWorkflow

pytestmark = pytest.mark.asyncio(loop_scope="session")


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
    assert result.state == "failed" and "No Bundle repo" in result.error


async def test_revise_replaces_content_and_keeps_history(env, worker, uid):
    await start_bundle(env, f"b{uid}")
    p = await start_proposal(env, f"b{uid}", f"r{uid}")
    [change] = (await wait_state(p, "awaiting_review")).changes
    original = change.content

    await p.execute_update(ProposalWorkflow.revise, args=[change.id, "Mention LU 2 as fallback.", "lee"])
    view = await wait_state(p, "awaiting_review")
    [revised] = view.changes
    assert "Revision: Mention LU 2 as fallback." in revised.content
    assert [(h.replaced_by, h.note, h.by, h.content) for h in revised.history] == [
        ("revise", "Mention LU 2 as fallback.", "lee", original)
    ]
    assert view.runs == 2 and revised.decision == "pending"

    # Accepted changes cannot be revised until undone.
    await p.execute_update(ProposalWorkflow.decide, args=[change.id, "accepted"])
    with pytest.raises(WorkflowUpdateFailedError):
        await p.execute_update(ProposalWorkflow.revise, args=[change.id, "again", "lee"])


async def test_feedback_can_withdraw_pending_changes(env, worker, uid):
    await start_bundle(env, f"b{uid}")
    p = await start_proposal(env, f"b{uid}", f"f{uid}")
    await wait_state(p, "awaiting_review")
    await p.execute_update(ProposalWorkflow.feedback, args=["DELETE", "lee"])
    view = await wait_state(p, "awaiting_review")
    assert view.changes == []
    await p.execute_update(ProposalWorkflow.submit, "lee")
    assert (await p.result()).state == "discarded"


async def test_edit_rebases_a_stale_change(env, worker, settings, uid):
    await start_bundle(env, f"b{uid}")
    a = await start_proposal(env, f"b{uid}", f"a{uid}")
    b = await start_proposal(env, f"b{uid}", f"b{uid}")
    [ca] = (await wait_state(a, "awaiting_review")).changes
    [cb] = (await wait_state(b, "awaiting_review")).changes
    await a.execute_update(ProposalWorkflow.decide, args=[ca.id, "accepted"])
    await a.execute_update(ProposalWorkflow.submit, "lee")
    await a.result()

    await b.execute_update(ProposalWorkflow.decide, args=[cb.id, "accepted"])
    await b.execute_update(ProposalWorkflow.submit, "lee")
    stale = (await wait_state(b, "awaiting_review")).changes[0]
    assert stale.stale

    edited = stale.content.replace("Board boots from LU 1.", "Board boots from LU 1 (checked by park).")
    view = await b.execute_update(ProposalWorkflow.edit, args=[cb.id, edited, "park"])
    [c] = view.changes
    assert not c.stale and c.kind == "update" and c.edited_by == "park" and c.base_content
    await b.execute_update(ProposalWorkflow.decide, args=[cb.id, "accepted"])
    await b.execute_update(ProposalWorkflow.submit, "lee")
    assert (await b.result()).state == "done"
    text = (settings.bundles_dir / f"b{uid}" / c.path).read_text()
    assert "checked by park" in text
    log = git.git(settings.bundles_dir / f"b{uid}", "log", "-1", "--format=%B")
    assert "(edited by park)" in log
