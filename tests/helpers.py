import asyncio

from temporalio.common import SearchAttributePair, TypedSearchAttributes

from stonepedia import config, search
from stonepedia.models import BundleRun, BundleSpec, ProposalInput
from stonepedia.workflows import BundleWorkflow, ProposalWorkflow


async def start_bundle(env, slug):
    handle = await env.client.start_workflow(
        BundleWorkflow.run, BundleRun(spec=BundleSpec(slug=slug, name=slug)), id=f"bundle-{slug}", task_queue=config.TASK_QUEUE
    )
    await handle.execute_update(BundleWorkflow.wait_ready)
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


async def wait_state(handle, state, tries=100):
    for _ in range(tries):
        view = await handle.query(ProposalWorkflow.view)
        if view.state == state:
            return view
        await asyncio.sleep(0.1)
    raise AssertionError(f"state stayed {view.state} ({view.error}), wanted {state}")
