import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from stonepedia.deploy import render_compose


@pytest.mark.parametrize("port_override", [None, "9080"])
def test_generated_stack_needs_no_host_files_and_preserves_scripts(tmp_path, port_override):
    if not shutil.which("docker"):
        pytest.skip("Docker Compose is needed to validate config interpolation")
    repo = Path(__file__).resolve().parents[1]
    packaged = tmp_path / "packaged"
    packaged.mkdir()
    shutil.copy(repo / "docker-compose.yml", packaged)
    shutil.copytree(repo / "deploy/temporal", packaged / "temporal")
    image = "example/stonepedia:1.2.3"
    deployment = tmp_path / "server"
    deployment.mkdir()
    (deployment / "compose.yaml").write_text(render_compose(image, packaged))
    shutil.rmtree(packaged)
    env = {k: v for k, v in os.environ.items() if not k.startswith("COMPOSE_")}
    env.pop("STONEPEDIA_PORT", None)
    if port_override:
        env["STONEPEDIA_PORT"] = port_override
    result = subprocess.run(
        ["docker", "compose", "-f", "compose.yaml", "config", "--format", "json"],
        cwd=deployment, env=env, capture_output=True, text=True, check=True,
    )
    assert not result.stderr
    config = json.loads(result.stdout)
    services = config["services"]
    for name in ("web", "worker"):
        assert services[name]["image"] == image
    for name, service in services.items():
        assert "build" not in service
        assert all(volume["type"] == "volume" for volume in service.get("volumes", []))
        if name != "web":
            assert not service.get("ports")
    assert services["web"]["ports"][0]["published"] == (port_override or "8081")
    for service, filename in (
        ("temporal-schema", "setup-schema.sh"),
        ("temporal-init", "init.sh"),
        ("temporal", "dynamicconfig.yaml"),
    ):
        # `compose config` re-escapes dollars so its output can be loaded again.
        assert config["configs"][service]["content"].replace("$$", "$") == (
            repo / "deploy/temporal" / filename
        ).read_text()
