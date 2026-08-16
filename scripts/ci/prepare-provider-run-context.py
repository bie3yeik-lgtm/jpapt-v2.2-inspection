from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path

ZERO_SHA256 = "0" * 64
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
            "commit": nonempty_env("GITHUB_SHA", ZERO_SHA256),
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
        "revisions": {
            "reference": {"document_sha256": ZERO_SHA256},
            "evaluation_schema": {"document_sha256": ZERO_SHA256},
            "datasets": {"document_sha256": ZERO_SHA256},
            "runtime": {"document_sha256": ZERO_SHA256},
            "bundle_sha256": ZERO_SHA256,
        },
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
