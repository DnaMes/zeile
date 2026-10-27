"""Tests for the atomic release publishing in .github/workflows/release.yml."""

from __future__ import annotations

from typing import Any

import pytest

yaml = pytest.importorskip("yaml")


def _load_workflow() -> dict[str, Any]:
    with open(".github/workflows/release.yml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_creation_step_marks_release_as_draft() -> None:
    workflow = _load_workflow()
    create_step = next(
        step
        for step in workflow["jobs"]["validate-and-package"]["steps"]
        if step.get("name") == "Publish GitHub release"
    )
    assert "--draft" in create_step["run"]


def test_draft_false_appears_only_as_last_step_of_attach_packages() -> None:
    workflow = _load_workflow()
    occurrences: list[tuple[str, str]] = []
    for job_name, job in workflow["jobs"].items():
        steps = job.get("steps") or []
        for index, step in enumerate(steps, start=1):
            text = str(step.get("run", ""))
            if "--draft=false" in text:
                occurrences.append((job_name, str(step.get("name", f"step {index}"))))
                if job_name == "attach-packages":
                    assert index == len(steps), "publishing must be the last step"
    assert occurrences == [("attach-packages", "Publish the release")]


def test_needs_chain_keeps_strict_dependencies() -> None:
    workflow = _load_workflow()
    assert workflow["jobs"]["attach-packages"]["needs"] == "packages"
    assert workflow["jobs"]["packages"]["needs"] == "validate-and-package"


def test_no_job_runs_on_always() -> None:
    workflow = _load_workflow()
    for job_name, job in workflow["jobs"].items():
        assert "if" not in job, f"{job_name} must not use if: always()"
        for step in job.get("steps") or []:
            condition = str(step.get("if", ""))
            assert "always()" not in condition, f"{job_name} step must not be always()"
