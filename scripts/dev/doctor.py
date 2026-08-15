#!/usr/bin/env python3

"""
Development environment doctor.

This command verifies that the repository is internally consistent enough
to begin development or evaluation.

Checks include:

- repository layout
- Python version
- required Python packages
- TOML configuration
- evaluation JSON Schemas
- evaluation manifests
- expected/smoke.json
- runtime/cache directories
- materialized-audio cache configuration
- Hugging Face revision-lock staging
- ONNX Runtime availability and Execution Providers
- Git state

Exit status:

    0
        No fatal problems.

    1
        One or more required checks failed.

Warnings do not cause a non-zero exit status.
"""

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
from typing import Any


# -----------------------------------------------------------------------------
# Repository root
# -----------------------------------------------------------------------------


def find_repository_root() -> Path:
    override = os.environ.get(
        "PARAKEET_ONNX_REPO_ROOT"
    )

    if override:
        root = (
            Path(override)
            .expanduser()
            .resolve()
        )

        if (
            (root / "pyproject.toml").is_file()
            and (root / "config").is_dir()
        ):
            return root

        raise RuntimeError(
            "PARAKEET_ONNX_REPO_ROOT does not point "
            f"to a valid repository: {root}"
        )

    current = Path.cwd().resolve()

    for candidate in (
        current,
        *current.parents,
    ):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "config").is_dir()
        ):
            return candidate

    script = Path(__file__).resolve()

    for candidate in (
        script.parent,
        *script.parents,
    ):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "config").is_dir()
        ):
            return candidate

    raise RuntimeError(
        "Unable to locate repository root."
    )


ROOT = find_repository_root()


# -----------------------------------------------------------------------------
# Result model
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CheckResult:
    level: str
    name: str
    message: str


RESULTS: list[CheckResult] = []


def ok(
    name: str,
    message: str,
) -> None:
    RESULTS.append(
        CheckResult(
            level="OK",
            name=name,
            message=message,
        )
    )


def warn(
    name: str,
    message: str,
) -> None:
    RESULTS.append(
        CheckResult(
            level="WARN",
            name=name,
            message=message,
        )
    )


def fail(
    name: str,
    message: str,
) -> None:
    RESULTS.append(
        CheckResult(
            level="FAIL",
            name=name,
            message=message,
        )
    )


# -----------------------------------------------------------------------------
# Generic helpers
# -----------------------------------------------------------------------------


def package_version(
    package: str,
) -> str | None:
    try:
        return importlib.metadata.version(
            package
        )
    except importlib.metadata.PackageNotFoundError:
        return None


def load_json(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        value = json.load(file)

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "JSON root must be an object."
        )

    return value


def load_toml(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "rb",
    ) as file:
        return tomllib.load(file)


def run_command(
    command: list[str],
) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
    except (
        OSError,
        subprocess.CalledProcessError,
    ):
        return None

    return (
        result.stdout.strip()
        or None
    )


# -----------------------------------------------------------------------------
# Platform
# -----------------------------------------------------------------------------


def environment_id() -> str | None:
    mapping = {
        "Linux": "linux",
        "Windows": "windows",
        "Darwin": "macos",
    }

    return mapping.get(
        platform.system()
    )


def check_platform() -> None:
    environment = environment_id()

    if environment is None:
        fail(
            "platform",
            f"Unsupported OS: {platform.system()}",
        )
        return

    description = (
        f"{platform.system()} "
        f"{platform.release()} "
        f"{platform.machine()} "
        f"-> {environment}"
    )

    if (
        environment == "linux"
        and (
            "microsoft"
            in platform.release().lower()
            or "wsl"
            in platform.release().lower()
        )
    ):
        description += " (WSL detected)"

    ok(
        "platform",
        description,
    )


# -----------------------------------------------------------------------------
# Python
# -----------------------------------------------------------------------------


def check_python() -> None:
    version = sys.version_info

    if version < (3, 12):
        fail(
            "python",
            "Python >= 3.12 is required; "
            f"current={platform.python_version()}",
        )
        return

    ok(
        "python",
        (
            f"{platform.python_implementation()} "
            f"{platform.python_version()}"
        ),
    )


def check_python_packages() -> None:
    required = {
        "numpy": "core numerical arrays",
        "jsonschema": "evaluation schema validation",
        "soundfile": "audio decoding/materialization",
        "scipy": "canonical resampling",
    }

    optional = {
        "datasets": "Hugging Face dataset backend",
        "onnxruntime": "ONNX Runtime CPU/runtime evaluation",
        "onnxruntime-gpu": "CUDA-enabled ONNX Runtime distribution",
        "torch": "NeMo/reference frontend",
        "nemo_toolkit": "canonical NeMo reference runtime",
    }

    for package, purpose in required.items():
        version = package_version(
            package
        )

        if version is None:
            fail(
                f"package:{package}",
                f"Missing required package ({purpose}).",
            )
        else:
            ok(
                f"package:{package}",
                f"{version} ({purpose})",
            )

    for package, purpose in optional.items():
        version = package_version(
            package
        )

        if version is None:
            warn(
                f"package:{package}",
                f"Not installed ({purpose}).",
            )
        else:
            ok(
                f"package:{package}",
                f"{version} ({purpose})",
            )


# -----------------------------------------------------------------------------
# Repository layout
# -----------------------------------------------------------------------------


def check_repository_layout() -> None:
    required = [
        "config/models",
        "config/providers",
        "config/environments",
        "config/evaluation",
        "evaluation/schemas",
        "evaluation/manifests",
        "evaluation/expected",
        "python/src/parakeet_onnx",
        "python/src/parakeet_onnx/config",
        "python/src/parakeet_onnx/datasets",
        "python/src/parakeet_onnx/audio",
        "scripts/dev",
    ]

    missing = [
        item
        for item in required
        if not (
            ROOT / item
        ).exists()
    ]

    if missing:
        fail(
            "repository-layout",
            "Missing: "
            + ", ".join(missing),
        )
        return

    ok(
        "repository-layout",
        "Required development directories are present.",
    )


# -----------------------------------------------------------------------------
# Config TOML
# -----------------------------------------------------------------------------


def check_toml_configuration() -> None:
    expected_files = [
        "config/models/parakeet-tdt_ctc-0.6b-ja.toml",
        "config/models/kotoba-whisper-v2.0.toml",
        "config/providers/cpu.toml",
        "config/providers/cuda.toml",
        "config/providers/directml.toml",
        "config/providers/coreml.toml",
        "config/environments/linux.toml",
        "config/environments/windows.toml",
        "config/environments/macos.toml",
        "config/evaluation/smoke.toml",
        "config/evaluation/parity.toml",
        "config/evaluation/full.toml",
    ]

    for relative in expected_files:
        path = ROOT / relative

        if not path.is_file():
            fail(
                f"config:{relative}",
                "Configuration file is missing.",
            )
            continue

        try:
            value = load_toml(path)
        except Exception as exc:
            fail(
                f"config:{relative}",
                f"Invalid TOML: {exc}",
            )
            continue

        if value.get(
            "schema_version"
        ) != 1:
            fail(
                f"config:{relative}",
                "schema_version must equal 1.",
            )
            continue

        ok(
            f"config:{relative}",
            "valid TOML",
        )


def check_environment_audio_cache() -> None:
    files = [
        ROOT
        / "config"
        / "environments"
        / f"{name}.toml"
        for name in (
            "linux",
            "windows",
            "macos",
        )
    ]

    for path in files:
        if not path.is_file():
            continue

        try:
            value = load_toml(
                path
            )
        except Exception:
            continue

        path_config = value.get(
            "path",
            {},
        )

        actual = path_config.get(
            "materialized_audio_cache"
        )

        if actual is None:
            warn(
                f"audio-cache:{path.name}",
                (
                    "path.materialized_audio_cache is not configured. "
                    "Recommended value: .cache/evaluation/audio"
                ),
            )
            continue

        if (
            actual
            != ".cache/evaluation/audio"
        ):
            warn(
                f"audio-cache:{path.name}",
                (
                    "Materialized audio cache differs from the "
                    f"project default: {actual}"
                ),
            )
            continue

        ok(
            f"audio-cache:{path.name}",
            actual,
        )


# -----------------------------------------------------------------------------
# JSON Schemas
# -----------------------------------------------------------------------------


def check_json_schemas() -> None:
    try:
        from jsonschema import (
            Draft202012Validator,
        )
    except ImportError:
        fail(
            "schemas",
            "jsonschema package is unavailable.",
        )
        return

    schema_files = [
        "manifest.schema.json",
        "expected.schema.json",
        "run-context.schema.json",
        "result.schema.json",
        "benchmark.schema.json",
    ]

    root = (
        ROOT
        / "evaluation"
        / "schemas"
    )

    for filename in schema_files:
        path = root / filename

        if not path.is_file():
            fail(
                f"schema:{filename}",
                "Schema file is missing.",
            )
            continue

        try:
            schema = load_json(
                path
            )

            Draft202012Validator.check_schema(
                schema
            )

        except Exception as exc:
            fail(
                f"schema:{filename}",
                f"Invalid JSON Schema: {exc}",
            )
            continue

        ok(
            f"schema:{filename}",
            "valid Draft 2020-12 schema",
        )


# -----------------------------------------------------------------------------
# Manifests
# -----------------------------------------------------------------------------


def check_manifests() -> None:
    try:
        from jsonschema import (
            Draft202012Validator,
        )
    except ImportError:
        return

    schema_path = (
        ROOT
        / "evaluation"
        / "schemas"
        / "manifest.schema.json"
    )

    if not schema_path.is_file():
        return

    try:
        validator = Draft202012Validator(
            load_json(schema_path)
        )
    except Exception:
        return

    manifests = {
        "smoke.jsonl": 12,
        "parity.jsonl": 48,
        "coreml-parity.jsonl": 40,
        "full.jsonl": 768,
    }

    manifest_root = (
        ROOT
        / "evaluation"
        / "manifests"
    )

    for filename, expected_count in manifests.items():
        path = (
            manifest_root
            / filename
        )

        if not path.is_file():
            fail(
                f"manifest:{filename}",
                "Manifest is missing.",
            )
            continue

        total = 0
        valid = True

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            for line_number, line in enumerate(
                file,
                start=1,
            ):
                line = line.strip()

                if not line:
                    continue

                try:
                    value = json.loads(
                        line
                    )
                except json.JSONDecodeError as exc:
                    fail(
                        f"manifest:{filename}",
                        (
                            f"line {line_number}: "
                            f"invalid JSON: {exc}"
                        ),
                    )
                    valid = False
                    break

                errors = list(
                    validator.iter_errors(
                        value
                    )
                )

                if errors:
                    fail(
                        f"manifest:{filename}",
                        (
                            f"line {line_number}: "
                            f"{errors[0].message}"
                        ),
                    )
                    valid = False
                    break

                total += int(
                    value["selection"]["count"]
                )

        if not valid:
            continue

        if total != expected_count:
            fail(
                f"manifest:{filename}",
                (
                    f"Expected {expected_count} samples, "
                    f"manifest requests {total}."
                ),
            )
            continue

        ok(
            f"manifest:{filename}",
            f"valid; deterministic sample count={total}",
        )


# -----------------------------------------------------------------------------
# Expected smoke output
# -----------------------------------------------------------------------------


def check_expected_smoke() -> None:
    expected_path = (
        ROOT
        / "evaluation"
        / "expected"
        / "smoke.json"
    )

    schema_path = (
        ROOT
        / "evaluation"
        / "schemas"
        / "expected.schema.json"
    )

    if not expected_path.is_file():
        fail(
            "expected:smoke",
            "evaluation/expected/smoke.json is missing.",
        )
        return

    if not schema_path.is_file():
        return

    try:
        from jsonschema import (
            Draft202012Validator,
        )

        expected = load_json(
            expected_path
        )

        schema = load_json(
            schema_path
        )

        errors = list(
            Draft202012Validator(
                schema
            ).iter_errors(
                expected
            )
        )

    except Exception as exc:
        fail(
            "expected:smoke",
            f"Unable to validate expected data: {exc}",
        )
        return

    if errors:
        fail(
            "expected:smoke",
            errors[0].message,
        )
        return

    status = expected.get(
        "status"
    )

    if status == "uninitialized":
        warn(
            "expected:smoke",
            (
                "Schema-valid but uninitialized. "
                "Pinned HF revisions/reference outputs are still required "
                "before smoke parity can be authoritative."
            ),
        )
    else:
        ok(
            "expected:smoke",
            "ready and schema-valid",
        )


# -----------------------------------------------------------------------------
# Runtime/cache directories
# -----------------------------------------------------------------------------


def check_runtime_directories() -> None:
    directories = [
        ".cache",
        ".cache/models",
        ".cache/evaluation",
        ".cache/evaluation/audio",
        ".cache/huggingface",
        ".ci",
        "results",
        "tmp",
    ]

    for relative in directories:
        path = ROOT / relative

        if not path.exists():
            warn(
                f"directory:{relative}",
                "Not created yet. Run scripts/dev/setup.",
            )
            continue

        if not path.is_dir():
            fail(
                f"directory:{relative}",
                "Expected a directory.",
            )
            continue

        ok(
            f"directory:{relative}",
            path.as_posix(),
        )


# -----------------------------------------------------------------------------
# HF revision staging
# -----------------------------------------------------------------------------


def check_revision_staging() -> None:
    root = (
        ROOT
        / ".ci"
        / "hf"
        / "config"
        / "revisions"
    )

    required = [
        "reference.json",
        "evaluation-schema.json",
        "datasets-lock.json",
    ]

    if not root.is_dir():
        warn(
            "hf-revisions",
            (
                "HF revision staging directory is absent. "
                "This is expected before revisions are fetched."
            ),
        )
        return

    missing = [
        filename
        for filename in required
        if not (
            root / filename
        ).is_file()
    ]

    if missing:
        warn(
            "hf-revisions",
            "Not fetched: "
            + ", ".join(missing),
        )
        return

    for filename in required:
        path = (
            root
            / filename
        )

        try:
            load_json(path)
        except Exception as exc:
            fail(
                f"hf-revision:{filename}",
                f"Invalid JSON: {exc}",
            )
        else:
            ok(
                f"hf-revision:{filename}",
                "staged and valid JSON",
            )


# -----------------------------------------------------------------------------
# ONNX Runtime
# -----------------------------------------------------------------------------


def check_onnxruntime() -> None:
    try:
        import onnxruntime as ort
    except ImportError:
        warn(
            "onnxruntime",
            (
                "onnxruntime is not installed. "
                "Configuration/dataset development remains possible, "
                "but ONNX evaluation cannot run."
            ),
        )
        return

    providers = (
        ort.get_available_providers()
    )

    ok(
        "onnxruntime",
        (
            f"version={ort.__version__}; "
            f"providers={providers}"
        ),
    )

    environment = environment_id()

    expected_provider = {
        "linux": "CPUExecutionProvider",
        "windows": "CPUExecutionProvider",
        "macos": "CPUExecutionProvider",
    }.get(environment)

    if (
        expected_provider is not None
        and expected_provider
        not in providers
    ):
        fail(
            "onnxruntime:cpu",
            (
                "CPUExecutionProvider is unexpectedly unavailable."
            ),
        )
    else:
        ok(
            "onnxruntime:cpu",
            "CPUExecutionProvider available",
        )

    if environment == "macos":
        if (
            "CoreMLExecutionProvider"
            in providers
        ):
            ok(
                "onnxruntime:coreml",
                "CoreMLExecutionProvider available",
            )
        else:
            warn(
                "onnxruntime:coreml",
                (
                    "CoreMLExecutionProvider is not exposed by the "
                    "installed ONNX Runtime build."
                ),
            )

    if environment == "windows":
        if (
            "DmlExecutionProvider"
            in providers
        ):
            ok(
                "onnxruntime:directml",
                "DmlExecutionProvider available",
            )
        else:
            warn(
                "onnxruntime:directml",
                (
                    "DmlExecutionProvider is not exposed by the "
                    "installed ONNX Runtime build."
                ),
            )

    if environment in (
        "linux",
        "windows",
    ):
        if (
            "CUDAExecutionProvider"
            in providers
        ):
            ok(
                "onnxruntime:cuda",
                "CUDAExecutionProvider available",
            )
        else:
            warn(
                "onnxruntime:cuda",
                "CUDAExecutionProvider unavailable.",
            )


# -----------------------------------------------------------------------------
# Git
# -----------------------------------------------------------------------------


def check_git() -> None:
    version = run_command(
        [
            "git",
            "--version",
        ]
    )

    if version is None:
        fail(
            "git",
            "Git is unavailable.",
        )
        return

    commit = run_command(
        [
            "git",
            "-C",
            str(ROOT),
            "rev-parse",
            "HEAD",
        ]
    )

    if commit is None:
        warn(
            "git",
            f"{version}; repository commit unavailable",
        )
        return

    dirty = run_command(
        [
            "git",
            "-C",
            str(ROOT),
            "status",
            "--porcelain",
        ]
    )

    state = (
        "dirty"
        if dirty
        else "clean"
    )

    ok(
        "git",
        f"{version}; {commit[:12]}; working tree={state}",
    )


# -----------------------------------------------------------------------------
# Project package
# -----------------------------------------------------------------------------


def check_project_import() -> None:
    try:
        import parakeet_onnx
    except Exception as exc:
        fail(
            "project-import",
            f"Unable to import parakeet_onnx: {exc}",
        )
        return

    ok(
        "project-import",
        str(
            Path(
                parakeet_onnx.__file__
            ).resolve()
        ),
    )


# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------


def print_report() -> None:
    print()
    print(
        "Parakeet ONNX Development Doctor"
    )
    print(
        "=" * 36
    )
    print(
        f"Repository: {ROOT}"
    )
    print()

    widths = {
        "level": max(
            [len(result.level) for result in RESULTS]
            + [5]
        ),
        "name": max(
            [len(result.name) for result in RESULTS]
            + [4]
        ),
    }

    for result in RESULTS:
        print(
            f"{result.level:<{widths['level']}}  "
            f"{result.name:<{widths['name']}}  "
            f"{result.message}"
        )

    counts = {
        level: sum(
            result.level == level
            for result in RESULTS
        )
        for level in (
            "OK",
            "WARN",
            "FAIL",
        )
    }

    print()
    print(
        "Summary: "
        f"OK={counts['OK']} "
        f"WARN={counts['WARN']} "
        f"FAIL={counts['FAIL']}"
    )


def main() -> int:
    check_platform()
    check_python()
    check_repository_layout()
    check_project_import()

    check_python_packages()

    check_toml_configuration()
    check_environment_audio_cache()

    check_json_schemas()
    check_manifests()
    check_expected_smoke()

    check_runtime_directories()
    check_revision_staging()

    check_onnxruntime()
    check_git()

    print_report()

    has_failure = any(
        result.level == "FAIL"
        for result in RESULTS
    )

    return (
        1
        if has_failure
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
