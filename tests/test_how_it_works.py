"""The "How it works" page must chart every Temporal workflow."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _workflow_classes() -> list[str]:
    tree = ast.parse((ROOT / "src/stonepedia/workflows.py").read_text())
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(ast.unparse(d).startswith("workflow.defn") for d in node.decorator_list)
    ]


def test_every_workflow_has_a_chart():
    page = (ROOT / "web/src/pages/HowItWorks.tsx").read_text()
    workflows = _workflow_classes()
    assert len(workflows) >= 4
    missing = [name for name in workflows if f"workflow: '{name}'" not in page]
    assert not missing, f"Add a chart for {missing} to web/src/pages/HowItWorks.tsx"
