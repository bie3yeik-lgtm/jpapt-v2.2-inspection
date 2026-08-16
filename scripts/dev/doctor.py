#!/usr/bin/env python3
"""Fast repository consistency checks using the canonical project loaders."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tomllib


def find_repository_root() -> Path:
    override = os.environ.get("PARAKEET_ONNX_REPO_ROOT")
    starts = [Path(override).expanduser().resolve()] if override else []
    starts += [Path.cwd().resolve(), Path(__file__).resolve()]
    for start in starts:
        for candidate in (start, *start.parents):
            if (candidate / "pyproject.toml").is_file() and (candidate / "config").is_dir():
                return candidate
    raise RuntimeError("Unable to locate repository root.")


ROOT = find_repository_root()


@dataclass(frozen=True, slots=True)
class CheckResult:
    level: str
    name: str
    message: str


RESULTS: list[CheckResult] = []


def _record(level: str, name: str, message: str) -> None:
    RESULTS.append(CheckResult(level, name, message))


def ok(name: str, message: str) -> None:
    _record("OK", name, message)


def warn(name: str, message: str) -> None:
    _record("WARN", name, message)


def fail(name: str, message: str) -> None:
    _record("FAIL", name, message)


def check_platform() -> None:
    mapping = {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}
    environment = mapping.get(platform.system())
    if environment is None:
        fail("platform", f"Unsupported OS: {platform.system()}")
    else:
        ok("platform", f"{platform.system()} {platform.machine()} -> {environment}")


def check_python() -> None:
    if sys.version_info < (3, 12):
        fail("python", f"Python >= 3.12 required; current={platform.python_version()}")
    else:
        ok("python", platform.python_version())


def check_project_import() -> None:
    try:
        import parakeet_onnx
    except Exception as exc:
        fail("project-import", str(exc))
    else:
        ok("project-import", str(Path(parakeet_onnx.__file__).resolve()))


def check_python_packages() -> None:
    for package in ("numpy", "jsonschema", "soundfile", "scipy"):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            fail(f"package:{package}", "missing")
        else:
            ok(f"package:{package}", version)
    for package in ("datasets", "onnx", "onnxruntime"):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            warn(f"package:{package}", "not installed")
        else:
            ok(f"package:{package}", version)


def check_toml_configuration() -> None:
    roots = (
        ROOT / "config" / "models",
        ROOT / "config" / "providers",
        ROOT / "config" / "environments",
        ROOT / "config" / "evaluation",
        ROOT / "config" / "hf-targets",
        ROOT / "config" / "evaluators",
    )
    for directory in roots:
        if not directory.is_dir():
            fail("config", f"missing directory: {directory.relative_to(ROOT)}")
            continue
        for path in sorted(directory.glob("*.toml")):
            try:
                with path.open("rb") as handle:
                    tomllib.load(handle)
            except Exception as exc:
                fail(f"config:{path.name}", str(exc))
            else:
                ok(f"config:{path.name}", "valid TOML")


def check_json_schemas() -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        fail("schemas", "jsonschema unavailable")
        return
    root = ROOT / "evaluation" / "schemas"
    for path in sorted(root.glob("*.schema.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            fail(f"schema:{path.name}", str(exc))
        else:
            ok(f"schema:{path.name}", "valid Draft 2020-12 schema")


def check_manifests() -> None:
    from parakeet_onnx.datasets.manifest import ManifestLoader

    expected = {
        "smoke.jsonl": 12,
        "parity.jsonl": 48,
        "coreml-parity.jsonl": 40,
        "full.jsonl": 768,
    }
    loader = ManifestLoader(ROOT)
    for filename, expected_count in expected.items():
        path = ROOT / "evaluation" / "manifests" / filename
        try:
            entries = loader.load(path)
            actual = loader.expected_sample_count(entries)
        except Exception as exc:
            fail(f"manifest:{filename}", str(exc))
            continue
        if actual != expected_count:
            fail(
                f"manifest:{filename}",
                f"expected {expected_count} samples, manifest requests {actual}",
            )
        else:
            ok(f"manifest:{filename}", f"valid; deterministic sample count={actual}")


def check_expected_smoke() -> None:
    from jsonschema import Draft202012Validator

    value_path = ROOT / "evaluation" / "expected" / "smoke.json"
    schema_path = ROOT / "evaluation" / "schemas" / "expected.schema.json"
    try:
        value = json.loads(value_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema).iter_errors(value))
    except Exception as exc:
        fail("expected:smoke", str(exc))
        return
    if errors:
        fail("expected:smoke", errors[0].message)
    elif value.get("status") == "uninitialized":
        warn("expected:smoke", "schema-valid but uninitialized")
    else:
        ok("expected:smoke", "ready and schema-valid")


def check_revision_staging() -> None:
    root = ROOT / ".ci" / "hf" / "config" / "revisions"
    required = (
        "reference.json",
        "evaluation-schema.json",
        "datasets-lock.json",
        "runtime.json",
    )
    if not root.is_dir():
        warn("hf-revisions", "not fetched yet")
        return
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        warn("hf-revisions", "not fetched: " + ", ".join(missing))
        return
    try:
        from parakeet_onnx.hf.revisions import load_revision_bundle

        load_revision_bundle(root)
    except Exception as exc:
        fail("hf-revisions", str(exc))
    else:
        ok("hf-revisions", "canonical four-document bundle is valid")


def check_onnxruntime() -> None:
    try:
        import onnxruntime as ort
    except ImportError:
        warn("onnxruntime", "not installed")
        return
    providers = ort.get_available_providers()
    if "CPUExecutionProvider" not in providers:
        fail("onnxruntime", f"CPUExecutionProvider unavailable: {providers}")
    else:
        ok("onnxruntime", f"version={ort.__version__}; providers={providers}")


def check_git() -> None:
    try:
        commit = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception as exc:
        warn("git", str(exc))
    else:
        ok("git", commit[:12])


def print_report() -> None:
    print("\nParakeet ONNX Development Doctor")
    print("=" * 36)
    for result in RESULTS:
        print(f"{result.level:5}  {result.name:36}  {result.message}")
    counts = {level: sum(item.level == level for item in RESULTS) for level in ("OK", "WARN", "FAIL")}
    print(f"\nSummary: OK={counts['OK']} WARN={counts['WARN']} FAIL={counts['FAIL']}")


def main() -> int:
    check_platform()
    check_python()
    check_project_import()
    check_python_packages()
    check_toml_configuration()
    check_json_schemas()
    check_manifests()
    check_expected_smoke()
    check_revision_staging()
    check_onnxruntime()
    check_git()
    print_report()
    return 1 if any(item.level == "FAIL" for item in RESULTS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
