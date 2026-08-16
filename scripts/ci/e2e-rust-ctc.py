from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path


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


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_string(source: dict[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"reference result requires non-empty {key!r}")
    return value


def revision_snapshot(
    contract: dict[str, object],
    reference: dict[str, object],
) -> dict[str, object]:
    catalog = contract.get("catalog")
    if not isinstance(catalog, dict):
        raise RuntimeError("candidate contract must contain catalog identity")

    model_id = require_string(reference, "model_id")
    model_revision = require_string(reference, "model_revision")
    dataset_id = require_string(reference, "dataset_id")
    dataset_revision = require_string(reference, "dataset_revision")
    sample_file = require_string(reference, "sample_file")
    sample_sha256 = require_string(reference, "sample_sha256")
    profile_set = require_string(contract, "profile_set")

    runtime_document = {
        "schema_version": 1,
        "catalog": {
            "id": require_string(catalog, "id"),
            "sha256": require_string(catalog, "sha256"),
        },
        "profile_set": profile_set,
    }
    reference_document = {
        "schema_version": 1,
        "development_artifact": {"repo_id": model_id, "revision": model_revision},
        "upstream": {"repo_id": model_id, "revision": model_revision},
        "tokenizer": {"repo_id": model_id, "revision": model_revision},
        "reference": {
            "id": "public-model-ctc-reference",
            "revision": model_revision,
            "canonical_framework": "transformers",
        },
    }
    evaluation_document = {
        "schema_version": 1,
        "schema": {
            "id": "public-model-e2e-smoke",
            "revision": "public-model-e2e-v1",
        },
        "artifact_contract": "ctc-single-graph-v1",
    }
    datasets_document = {
        "schema_version": 1,
        "datasets": [
            {
                "id": "jsut-basic5000",
                "repo_id": dataset_id,
                "revision": dataset_revision,
                "subset": "default",
                "split": "sample",
                "sha256": sample_sha256,
                "manifest": sample_file,
            }
        ],
    }

    reference_hash = canonical_sha256(reference_document)
    evaluation_hash = canonical_sha256(evaluation_document)
    datasets_hash = canonical_sha256(datasets_document)
    runtime_hash = canonical_sha256(runtime_document)
    bundle_digest = hashlib.sha256()
    for document_hash in (
        reference_hash,
        evaluation_hash,
        datasets_hash,
        runtime_hash,
    ):
        bundle_digest.update(document_hash.encode("ascii"))

    return {
        "config_version": "public-model-e2e-v1",
        "bundle_sha256": bundle_digest.hexdigest(),
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
            "reference_id": "public-model-ctc-reference",
            "reference_revision": model_revision,
            "canonical_framework": "transformers",
        },
        "evaluation_schema": {
            "document_sha256": evaluation_hash,
            "schema_id": "public-model-e2e-smoke",
            "schema_revision": "public-model-e2e-v1",
        },
        "datasets": {
            "document_sha256": datasets_hash,
            "entries": datasets_document["datasets"],
        },
    }


def prepare(contract_path: Path, reference_path: Path, output: Path) -> None:
    contract = load_json(contract_path)
    reference = load_json(reference_path)
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
    model_id = require_string(reference, "model_id")
    context = {
        "schema_version": 2,
        "run_id": "public-model-rust-ctc-e2e",
        "created_at": "2026-08-16T00:00:00Z",
        "config_identity": "public-model-e2e-v1",
        "model_id": model_id,
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
            "commit": nonempty_env("GITHUB_SHA", "0000000000000000000000000000000000000000"),
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
        "revisions": revision_snapshot(contract, reference),
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
            "hf_model_revision": require_string(reference, "model_revision"),
            "hf_dataset_revision": require_string(reference, "dataset_revision"),
            "sample_sha256": require_string(reference, "sample_sha256"),
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
                "model_revision": reference.get("model_revision"),
                "dataset_revision": reference.get("dataset_revision"),
                "sample_sha256": reference.get("sample_sha256"),
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
    prepare_parser.add_argument("--reference", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--reference", type=Path, required=True)
    validate_parser.add_argument("--samples", type=Path, required=True)
    validate_parser.add_argument("--metrics", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "prepare":
        prepare(args.contract, args.reference, args.output)
    else:
        validate(args.reference, args.samples, args.metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
