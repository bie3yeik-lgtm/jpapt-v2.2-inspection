from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import subprocess

ORT_NAMES = {
    "cpu": "CPUExecutionProvider",
    "cuda": "CUDAExecutionProvider",
    "directml": "DmlExecutionProvider",
    "coreml": "CoreMLExecutionProvider",
}


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def host_os_id() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    raise RuntimeError(f"unsupported host operating system: {system}")


def nonempty_env(name: str, fallback: str) -> str:
    return os.environ.get(name) or fallback


def git_commit() -> str:
    value = os.environ.get("GITHUB_SHA")
    if not value:
        try:
            value = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("provider probe requires a concrete Git commit") from exc
    if re.fullmatch(r"[0-9a-fA-F]{7,64}", value) is None:
        raise RuntimeError(f"invalid Git commit identity: {value!r}")
    return value.lower()


def revision_snapshot(contract: dict[str, object]) -> dict[str, object]:
    catalog = contract.get("catalog")
    if not isinstance(catalog, dict):
        raise RuntimeError("candidate contract must contain catalog identity")
    profile_set = str(contract["profile_set"])
    runtime_document = {
        "schema_version": 1,
        "catalog": {
            "id": str(catalog["id"]),
            "sha256": str(catalog["sha256"]),
        },
        "profile_set": profile_set,
    }
    reference_document = {
        "schema_version": 1,
        "development_artifact": {
            "repo_id": "generated/provider-probe",
            "revision": "synthetic-v1",
        },
        "upstream": {
            "repo_id": "generated/provider-probe",
            "revision": "synthetic-v1",
        },
        "tokenizer": {
            "repo_id": "generated/provider-probe-tokenizer",
            "revision": "synthetic-v1",
        },
        "reference": {
            "id": "provider-probe-reference",
            "revision": "synthetic-v1",
            "canonical_framework": "generated",
        },
    }
    evaluation_document = {
        "schema_version": 1,
        "schema": {"id": "provider-probe-smoke", "revision": "synthetic-v1"},
        "artifact_contract": "ctc-single-graph-v1",
    }
    datasets_document = {"schema_version": 1, "datasets": []}

    reference_hash = canonical_sha256(reference_document)
    evaluation_hash = canonical_sha256(evaluation_document)
    datasets_hash = canonical_sha256(datasets_document)
    runtime_hash = canonical_sha256(runtime_document)
    bundle = hashlib.sha256()
    for document_hash in (
        reference_hash,
        evaluation_hash,
        datasets_hash,
        runtime_hash,
    ):
        bundle.update(document_hash.encode("ascii"))

    return {
        "config_version": "provider-probe-v1",
        "bundle_sha256": bundle.hexdigest(),
        "runtime": {
            "document_sha256": runtime_hash,
            "catalog": runtime_document["catalog"],
            "profile_set": profile_set,
        },
        "reference": {
            "document_sha256": reference_hash,
            "development_artifact": reference_document["development_artifact"],
            "upstream": reference_document["upstream"],
            "tokenizer": reference_document["tokenizer"],
            "reference_id": "provider-probe-reference",
            "reference_revision": "synthetic-v1",
            "canonical_framework": "generated",
        },
        "evaluation_schema": {
            "document_sha256": evaluation_hash,
            "schema_id": "provider-probe-smoke",
            "schema_revision": "synthetic-v1",
        },
        "datasets": {
            "document_sha256": datasets_hash,
            "entries": [],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--provider", choices=sorted(ORT_NAMES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_json(args.contract)
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("primary"), dict):
        raise RuntimeError("candidate contract must contain primary artifact")
    primary = artifacts["primary"]
    candidate_root = Path(str(contract["candidate_root"]))
    model_path = candidate_root / str(primary["path"])
    if not model_path.is_file():
        raise RuntimeError(f"candidate primary artifact is missing: {model_path}")

    candidate_id = str(contract["candidate_id"])
    host_os = host_os_id()
    context = {
        "schema_version": 2,
        "run_id": f"strict-provider-probe-{args.provider}",
        "created_at": "2026-08-16T00:00:00Z",
        "config_identity": "strict-provider-probe-v1",
        "model_id": "synthetic-strict-provider-ctc",
        "environment_id": host_os,
        "provider_id": args.provider,
        "evaluation_id": "smoke",
        "artifact": {
            "path": str(model_path.resolve()),
            "sha256": str(primary["sha256"]),
            "size_bytes": int(primary["size_bytes"]),
            "candidate_id": candidate_id,
            "artifact_role": "primary",
        },
        "git": {
            "repository": "bie3yeik-lgtm/jpapt-v2.2-inspection",
            "commit": git_commit(),
            "ref": nonempty_env("GITHUB_REF_NAME", "agent/provider-strict-probes"),
            "dirty": False,
        },
        "host": {
            "os": host_os,
            "architecture": platform.machine() or "unknown",
            "hostname": platform.node() or "github-runner",
            "python_version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "is_wsl": False,
            "github_runner_os": nonempty_env("RUNNER_OS", host_os),
            "github_runner_arch": nonempty_env("RUNNER_ARCH", platform.machine() or "unknown"),
            "github_run_id": nonempty_env("GITHUB_RUN_ID", "local"),
            "github_run_attempt": nonempty_env("GITHUB_RUN_ATTEMPT", "1"),
        },
        "runtime": {
            "implementation": "rust",
            "backend": "onnxruntime",
            "backend_version": "resolved-by-rust-runtime",
            "provider_id": args.provider,
            "provider_ort_name": ORT_NAMES[args.provider],
            "provider_available": False,
        },
        "revisions": revision_snapshot(contract),
        "config": {
            "resolved": {
                "provider": {
                    "session": {
                        "graph_optimization_level": "all",
                        "execution_mode": "sequential",
                        "enable_mem_pattern": True,
                    },
                    "validation": {
                        "allow_cpu_fallback": False,
                        "strict_provider_mode": True,
                    },
                },
                "environment": {
                    "runtime": {
                        "cpu": {"intra_op_threads": 0, "inter_op_threads": 0}
                    }
                },
            }
        },
        "metadata": {
            "candidate": contract,
            "purpose": "strict non-CPU execution-provider readiness probe",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
