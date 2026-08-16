from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path

ZERO_SHA256 = "0" * 64


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def nonempty_env(name: str, fallback: str) -> str:
    return os.environ.get(name) or fallback


def reject_nulls(value: object, path: str = "$") -> None:
    if value is None:
        raise RuntimeError(f"Rust E2E run-context must not contain null: {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            reject_nulls(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_nulls(item, f"{path}[{index}]")


def prepare(contract_path: Path, output: Path) -> None:
    contract = load_json(contract_path)
    candidate_root = Path(str(contract["candidate_root"]))
    artifacts = contract["artifacts"]
    if not isinstance(artifacts, dict):
        raise RuntimeError("candidate contract artifacts must be an object")
    primary = artifacts.get("primary")
    if not isinstance(primary, dict):
        raise RuntimeError("candidate contract must contain primary artifact")
    model_path = candidate_root / str(primary["path"])
    if not model_path.is_file():
        raise RuntimeError(f"candidate primary artifact is missing: {model_path}")

    candidate_id = str(contract["candidate_id"])
    context = {
        "schema_version": 2,
        "run_id": "public-model-rust-ctc-e2e",
        "created_at": "2026-08-16T00:00:00Z",
        "config_identity": "public-model-e2e-v1",
        "model_id": "TKU410410103/wav2vec2-base-japanese-asr",
        "environment_id": "linux",
        "provider_id": "cpu",
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
            "os": "linux",
            "architecture": platform.machine() or "x86_64",
            "hostname": platform.node() or "github-runner",
            "python_version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "is_wsl": False,
            "github_runner_os": nonempty_env("RUNNER_OS", "linux"),
            "github_runner_arch": nonempty_env("RUNNER_ARCH", platform.machine() or "x86_64"),
            "github_run_id": nonempty_env("GITHUB_RUN_ID", "local"),
            "github_run_attempt": nonempty_env("GITHUB_RUN_ATTEMPT", "1"),
        },
        "runtime": {
            "implementation": "rust",
            "backend": "onnxruntime",
            "backend_version": "resolved-by-rust-runtime",
            "provider_id": "cpu",
            "provider_ort_name": "CPUExecutionProvider",
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
                        "allow_cpu_fallback": True,
                        "strict_provider_mode": False,
                    },
                },
                "environment": {
                    "runtime": {
                        "cpu": {
                            "intra_op_threads": 0,
                            "inter_op_threads": 0,
                        }
                    }
                },
            }
        },
        "metadata": {
            "candidate": contract,
            "purpose": "public real-model Rust CTC regression canary",
        },
    }
    reject_nulls(context)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate(result_path: Path, samples_path: Path, metrics_path: Path) -> None:
    reference = load_json(result_path)
    expected_text = str(reference["onnx_transcript"])

    lines = [line for line in samples_path.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) != 1:
        raise RuntimeError(f"expected exactly one Rust sample result, got {len(lines)}")
    sample = json.loads(lines[0])
    if sample.get("status") != "success":
        raise RuntimeError(f"Rust sample failed: {sample.get('errors')}")
    actual_text = sample.get("output", {}).get("text")
    if actual_text != expected_text:
        raise RuntimeError(
            f"Rust/ORT transcript mismatch: rust={actual_text!r}, ort={expected_text!r}"
        )

    metrics = load_json(metrics_path)
    acceptance = metrics.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("passed") is not True:
        raise RuntimeError(f"Rust metrics acceptance failed: {acceptance}")
    provider = metrics.get("provider")
    if not isinstance(provider, dict) or provider.get("execution_proven") is not True:
        raise RuntimeError(f"CPU execution was not proven: {provider}")

    print(
        json.dumps(
            {
                "rust_transcript": actual_text,
                "ort_transcript": expected_text,
                "transcript_parity": True,
                "provider": provider,
                "acceptance": acceptance,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--contract", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--reference", type=Path, required=True)
    validate_parser.add_argument("--samples", type=Path, required=True)
    validate_parser.add_argument("--metrics", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "prepare":
        prepare(args.contract, args.output)
    else:
        validate(args.reference, args.samples, args.metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
