"""Runs Claude Code headless (`claude -p`) in a sandbox: file tools only, confined to the workspace."""

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Callable

from stonepedia.agent import AgentConfigError, AgentError

TOOLS = "Read,Glob,Grep,Write,Edit"


def command(settings_file: Path) -> list[str]:
    binary = os.environ.get("STONEPEDIA_CLAUDE_BIN", "claude")
    if shutil.which(binary) is None:
        raise AgentConfigError(f"Claude Code CLI not found ({binary}). Is it installed in the worker image?")
    return [
        binary,
        "-p",
        "--restricted",  # no shell/web tools, ignores user/project settings, file tools stay in the workspace
        "--strict-mcp-config",
        "--tools", TOOLS,
        "--permission-mode", "acceptEdits",
        "--settings", str(settings_file),
        "--output-format", "json",
        "--no-session-persistence",
    ]


async def run(
    workspace: Path,
    prompt: str,
    settings_file: Path,
    timeout_s: float,
    heartbeat: Callable[[], None] = lambda: None,
) -> tuple[str, float | None]:
    """Returns (the agent's final message, cost in USD if reported)."""
    env = {
        **os.environ,
        "DISABLE_AUTOUPDATER": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    proc = await asyncio.create_subprocess_exec(
        *command(settings_file),
        cwd=workspace,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    talk = asyncio.ensure_future(proc.communicate(prompt.encode()))
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while not talk.done():
            if loop.time() > deadline:
                raise AgentError(f"Claude did not finish within {timeout_s / 60:.0f} minutes")
            await asyncio.wait([talk], timeout=10)
            heartbeat()
        stdout, stderr = talk.result()
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        talk.cancel()
        raise

    try:
        result = json.loads(stdout.decode() or "{}")
    except json.JSONDecodeError:
        result = {}
    message = str(result.get("result") or "").strip()
    if proc.returncode != 0 or result.get("is_error") or not result:
        detail = message or stderr.decode(errors="replace").strip()[-2000:] or stdout.decode(errors="replace")[-2000:]
        raise AgentError(f"Claude failed (exit {proc.returncode}): {detail or 'no output'}")
    return message, result.get("total_cost_usd")
