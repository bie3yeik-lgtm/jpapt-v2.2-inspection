#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
NAMESPACE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_repository(value: str) -> str:
    if not REPOSITORY_RE.fullmatch(value):
        raise ValueError("repository must use canonical owner/name format")
    owner, name = value.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError("repository must not contain dot-only path segments")
    return value


def validate_namespace(value: str) -> str:
    if not NAMESPACE_RE.fullmatch(value):
        raise ValueError("HF namespace must be one canonical namespace segment")
    if value in {".", ".."}:
        raise ValueError("HF namespace must not be a dot-only path segment")
    return value


def strict_bool(value: Any, *, default: bool, field: str) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value == "true":
            return True
        if value == "false":
            return False
    raise ValueError(f"{field} must be true or false")


def parse_payload(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as error:
        raise ValueError(f"repository_dispatch payload must be valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("repository_dispatch payload must be a JSON object")
    return value


def resolve_request(
    *,
    event_name: str,
    payload_json: str,
    repository_input: str,
    namespace_input: str,
    private_input: Any,
    write_input: Any,
    default_namespace: str,
) -> dict[str, Any]:
    if event_name == "repository_dispatch":
        payload = parse_payload(payload_json)
        repository = payload.get("repository", "")
        namespace = payload.get("hf_namespace", "")
        private_bucket = strict_bool(payload.get("private_bucket"), default=True, field="private_bucket")
        write_repo_config = strict_bool(
            payload.get("write_repo_config"),
            default=True,
            field="write_repo_config",
        )
        if not isinstance(repository, str) or not isinstance(namespace, str):
            raise ValueError("repository and hf_namespace must be strings")
    elif event_name == "workflow_dispatch":
        repository = repository_input
        namespace = namespace_input
        private_bucket = strict_bool(private_input, default=True, field="private_bucket")
        write_repo_config = strict_bool(write_input, default=True, field="write_repo_config")
    else:
        raise ValueError(f"unsupported bootstrap event: {event_name}")

    repository = validate_repository(repository)
    namespace = namespace or default_namespace
    if namespace:
        namespace = validate_namespace(namespace)

    return {
        "repository": repository,
        "namespace": namespace,
        "private_bucket": private_bucket,
        "write_repo_config": write_repo_config,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--event-name", required=True)
    resolve.add_argument("--payload-json", default="{}")
    resolve.add_argument("--repository-input", default="")
    resolve.add_argument("--namespace-input", default="")
    resolve.add_argument("--private-input", default="")
    resolve.add_argument("--write-input", default="")
    resolve.add_argument("--default-namespace", default="")

    namespace = subparsers.add_parser("namespace")
    namespace.add_argument("value")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "namespace":
            print(validate_namespace(args.value))
            return 0
        resolved = resolve_request(
            event_name=args.event_name,
            payload_json=args.payload_json,
            repository_input=args.repository_input,
            namespace_input=args.namespace_input,
            private_input=args.private_input,
            write_input=args.write_input,
            default_namespace=args.default_namespace,
        )
        print(json.dumps(resolved, sort_keys=True, separators=(",", ":")))
        return 0
    except ValueError as error:
        print(f"bootstrap request rejected: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
