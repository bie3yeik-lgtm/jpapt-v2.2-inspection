#!/usr/bin/env python3
"""Run deterministic repository checks inside the self-hosted Docker image."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path


ROOT = Path("/workspace")


def run(*command: str) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    required = [
        ".github/workflows/self-hosted-docker-smoke.yml",
        ".github/workflows/rtf-benchmark-run.yml",
        ".github/workflows/rtf-benchmark-contracts.yml",
        "docker/rtf-benchmark/Dockerfile",
        "docker/rtf-benchmark-smoke/Dockerfile",
        "docker/rtf-benchmark/entrypoint.sh",
        "scripts/ci/prepare-rtf-fixture.py",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"required repository files are missing: {missing}")

    workflow = read(".github/workflows/rtf-benchmark-run.yml")
    self_hosted_workflow = read(".github/workflows/self-hosted-docker-smoke.yml")
    entrypoint = read("docker/rtf-benchmark/entrypoint.sh")
    for marker in (
        "runs-on: self-hosted",
        "docker build --pull=false",
        "docker run --rm",
        'volume "${GITHUB_WORKSPACE}:/workspace:ro"',
        "if: always()",
    ):
        if marker not in self_hosted_workflow:
            raise SystemExit(f"self-hosted Docker workflow marker is missing: {marker}")
    for marker in (
        "Build and publish smoke fixture image",
        "RTF_FIXTURE_POINTER_MISMATCH",
        "RTF_FIXTURE_IMAGE_MISMATCH",
        "RTF_BUNDLED_FIXTURE_DIR",
        "PROVIDER_CUDA_DRIVER_INCOMPATIBLE",
    ):
        if marker not in workflow + entrypoint:
            raise SystemExit(f"RTF contract marker is missing: {marker}")

    for path in (
        "scripts/ci/prepare-rtf-fixture.py",
        "docker/rtf-benchmark/benchmark-runner/benchmark_runner/load_fixture.py",
    ):
        source = read(path)
        ast.parse(source, filename=path)
        if "from huggingface_hub import hf_hub_download" not in source:
            raise SystemExit(f"{path}: hf_hub_download import contract is missing")
        if "from huggingface_hub.utils import HfHubHTTPError" not in source:
            raise SystemExit(f"{path}: HfHubHTTPError import contract is missing")

    for path in (
        "scripts/ci/prepare-rtf-fixture.py",
        "scripts/ci/check-runpod-rtf-services.py",
        "docker/rtf-benchmark/benchmark-runner/benchmark_runner/cli.py",
    ):
        ast.parse(read(path), filename=path)

    for path in (
        "evaluation/schemas/rtf-service-result.schema.json",
        "evaluation/schemas/rtf-service-metrics.schema.json",
        "evaluation/schemas/rtf-provider-content.schema.json",
    ):
        json.loads(read(path))

    shell_files = [
        *sorted((ROOT / "scripts").rglob("*.sh")),
        ROOT / "docker/rtf-benchmark/entrypoint.sh",
    ]
    for path in shell_files:
        run("bash", "-n", str(path.relative_to(ROOT)))

    for path in sorted((ROOT / "evaluation/schemas").glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))

    print("self-hosted Docker RTF smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
