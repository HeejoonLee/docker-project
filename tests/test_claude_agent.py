"""The Claude runner, exercised against a stub `claude` executable."""

import json
import stat

import pytest

from helpers import start_bundle, start_proposal, wait_state
from stonepedia import appconfig

pytestmark = pytest.mark.asyncio(loop_scope="session")

STUB = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
prompt = sys.stdin.read()
log = os.environ["STUB_LOG"]
json.dump({"args": args, "prompt": prompt, "cwd": os.getcwd()}, open(log, "w"))
if os.environ.get("STUB_FAIL"):
    print(json.dumps({"is_error": True, "result": "Invalid API key"}))
    sys.exit(1)
os.makedirs("guides", exist_ok=True)
with open("guides/boot.md", "w") as f:
    f.write("---\\ntype: Guidance\\ntitle: Boot\\ndescription: d\\nstatus: final\\n---\\n\\n# Boot\\n")
with open(".stonepedia/template.yaml", "a") as f:
    f.write("# tampered\\n")
print(json.dumps({"is_error": False, "result": "Created guides/boot.md.", "total_cost_usd": 0.12}))
"""


@pytest.fixture
def stub_claude(tmp_path, settings, monkeypatch):
    stub = tmp_path / "claude-stub"
    stub.write_text(STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "stub-log.json"
    monkeypatch.setenv("STONEPEDIA_CLAUDE_BIN", str(stub))
    monkeypatch.setenv("STUB_LOG", str(log))
    appconfig.save(settings.config_dir, appconfig.AppConfig(agent="claude-cli"))
    appconfig.save_claude_settings(settings.config_dir, '{"env": {"ANTHROPIC_BASE_URL": "http://llm.intra"}}')
    return log


async def test_claude_run_becomes_article_changes(env, worker, settings, stub_claude, uid):
    await start_bundle(env, f"c{uid}")
    p = await start_proposal(env, f"c{uid}", f"c{uid}", title="Boot", text="Boot from LU 1.")
    view = await wait_state(p, "awaiting_review")

    [change] = view.changes  # the tampered template is ignored: not an Article
    assert change.path == "guides/boot.md" and change.kind == "create"
    assert "status: proposed" in change.content and "by: claude-code" in change.content
    assert view.summary == "Created guides/boot.md." and view.cost_usd == pytest.approx(0.12)

    call = json.loads(stub_claude.read_text())
    args = call["args"]
    assert "--restricted" in args and args[args.index("--tools") + 1] == "Read,Glob,Grep,Write,Edit"
    assert args[args.index("--settings") + 1] == str(settings.config_dir / "claude-settings.json")
    assert "Boot from LU 1." not in call["prompt"]  # material is passed as a file, not inline
    assert f"sources/c{uid}/text.md" in call["prompt"] and "Korean" in call["prompt"]
    assert f"resource: ../sources/c{uid}/text.md" in change.content  # cited, relative to guides/


async def test_claude_failure_is_reported(env, worker, stub_claude, monkeypatch, uid):
    monkeypatch.setenv("STUB_FAIL", "1")
    await start_bundle(env, f"e{uid}")
    p = await start_proposal(env, f"e{uid}", f"e{uid}")
    result = await p.result()
    assert result.state == "failed" and "Invalid API key" in result.error
