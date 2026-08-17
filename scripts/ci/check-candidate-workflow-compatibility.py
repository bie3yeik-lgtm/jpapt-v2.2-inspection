#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

COMMON_INPUTS = (
    "source_repository",
    "hf_bucket",
    "candidate_id",
    "package_name",
    "dataset_source",
    "dataset_id",
    "suite",
    "executor",
    "environment",
    "hf_flavor",
    "hf_jobs_image",
    "dry_run",
)
V2_ONLY_INPUTS = ("request_id", "receipt_repository")


def load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"workflow is not a YAML mapping: {path}")
    return value


def on_block(workflow: dict) -> dict:
    # PyYAML uses YAML 1.1 and may parse the key `on` as boolean True.
    value = workflow.get("on", workflow.get(True))
    if not isinstance(value, dict):
        raise SystemExit("workflow on block is missing")
    return value


def dispatch_inputs(workflow: dict) -> dict:
    dispatch = on_block(workflow).get("workflow_dispatch")
    if not isinstance(dispatch, dict):
        raise SystemExit("workflow_dispatch block is missing")
    inputs = dispatch.get("inputs", {})
    if not isinstance(inputs, dict):
        raise SystemExit("workflow_dispatch.inputs must be a mapping")
    return inputs


def normalized_contract(spec: dict) -> dict:
    result = {
        "type": spec.get("type", "string"),
        "required": bool(spec.get("required", False)),
        "default": spec.get("default"),
    }
    if result["type"] == "choice":
        result["options"] = list(spec.get("options", []))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", default=".github/workflows/candidate-package-evaluate.yml")
    parser.add_argument("--v2", default=".github/workflows/candidate-package-evaluate-v2.yml")
    parser.add_argument("--output")
    args = parser.parse_args()

    legacy = load(Path(args.legacy))
    v2 = load(Path(args.v2))
    legacy_inputs = dispatch_inputs(legacy)
    v2_inputs = dispatch_inputs(v2)

    errors: list[str] = []
    common: dict[str, dict] = {}
    for name in COMMON_INPUTS:
        if name not in legacy_inputs:
            errors.append(f"legacy workflow is missing common input {name}")
            continue
        if name not in v2_inputs:
            errors.append(f"V2 workflow is missing common input {name}")
            continue
        legacy_contract = normalized_contract(legacy_inputs[name])
        v2_contract = normalized_contract(v2_inputs[name])
        common[name] = {"legacy": legacy_contract, "v2": v2_contract}
        if legacy_contract != v2_contract:
            errors.append(
                f"input contract drift for {name}: legacy={legacy_contract!r} v2={v2_contract!r}"
            )

    for name in V2_ONLY_INPUTS:
        if name not in v2_inputs:
            errors.append(f"V2 workflow is missing protocol input {name}")

    legacy_on = on_block(legacy)
    repo_dispatch = legacy_on.get("repository_dispatch")
    event_types = []
    if isinstance(repo_dispatch, dict):
        raw_types = repo_dispatch.get("types", [])
        event_types = raw_types if isinstance(raw_types, list) else [raw_types]
    if "jpapt.candidate-evaluate" not in event_types:
        errors.append("legacy workflow no longer accepts jpapt.candidate-evaluate")

    report = {
        "schema_version": 1,
        "legacy_workflow": args.legacy,
        "v2_workflow": args.v2,
        "common_inputs": common,
        "v2_only_inputs": list(V2_ONLY_INPUTS),
        "legacy_repository_dispatch_types": event_types,
        "compatible": not errors,
        "errors": errors,
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if errors:
        raise SystemExit("legacy/V2 workflow input contracts are incompatible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
