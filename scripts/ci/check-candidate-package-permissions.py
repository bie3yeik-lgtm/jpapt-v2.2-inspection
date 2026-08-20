#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/candidate-package-evaluate-v2.yml")

EXPECTED_JOB_PERMISSIONS = {
    "build": {"contents": "read", "packages": "write"},
    "github-linux-cpu": {"contents": "read", "packages": "read"},
    "github-linux-cuda": {"contents": "read", "packages": "read"},
    "completion": {"contents": "write"},
}
NO_PACKAGE_JOBS = {
    "resolve",
    "github-macos-coreml",
    "github-windows-directml",
    "hf-jobs",
}


def fail(message: str) -> None:
    raise SystemExit(f"candidate package permission contract: {message}")


def main() -> int:
    value = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("workflow must be a YAML mapping")

    workflow_permissions = value.get("permissions")
    if workflow_permissions != {"contents": "read"}:
        fail(f"workflow-level permissions must be exactly contents: read; got {workflow_permissions!r}")

    jobs = value.get("jobs")
    if not isinstance(jobs, dict):
        fail("jobs must be a mapping")

    for job_name, expected in EXPECTED_JOB_PERMISSIONS.items():
        job = jobs.get(job_name)
        if not isinstance(job, dict):
            fail(f"missing job {job_name}")
        actual = job.get("permissions")
        if actual != expected:
            fail(f"{job_name} permissions must be {expected!r}; got {actual!r}")

    for job_name in NO_PACKAGE_JOBS:
        job = jobs.get(job_name)
        if not isinstance(job, dict):
            fail(f"missing job {job_name}")
        actual = job.get("permissions")
        if isinstance(actual, dict) and "packages" in actual:
            fail(f"{job_name} must not declare package permission; got {actual!r}")

    package_write_jobs = []
    package_read_jobs = []
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        permissions = job.get("permissions")
        if not isinstance(permissions, dict):
            continue
        package_permission = permissions.get("packages")
        if package_permission == "write":
            package_write_jobs.append(job_name)
        elif package_permission == "read":
            package_read_jobs.append(job_name)
        elif package_permission is not None:
            fail(f"{job_name} has unsupported packages permission {package_permission!r}")

    if package_write_jobs != ["build"]:
        fail(f"packages: write must be limited to build; got {package_write_jobs!r}")
    if sorted(package_read_jobs) != ["github-linux-cpu", "github-linux-cuda"]:
        fail(f"packages: read must be limited to Linux evaluation jobs; got {package_read_jobs!r}")

    print("candidate package permission contract: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
