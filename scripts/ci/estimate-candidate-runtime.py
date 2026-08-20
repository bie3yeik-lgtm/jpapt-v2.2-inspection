#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import math
import os
import statistics
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


def request(url: str, token: str, *, accept: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "jpapt-runtime-estimator",
        },
    )


def api_get(url: str, token: str) -> dict:
    with urllib.request.urlopen(request(url, token, accept="application/vnd.github+json"), timeout=30) as response:
        return json.load(response)


def api_bytes(url: str, token: str) -> bytes:
    with urllib.request.urlopen(request(url, token, accept="application/vnd.github+json"), timeout=30) as response:
        return response.read()


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def duration_minutes(job: dict) -> float | None:
    start = parse_time(job.get("started_at"))
    end = parse_time(job.get("completed_at"))
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() / 60.0


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def fallback_minutes(suite: str, executor: str, environment: str) -> int:
    base = {"probe": 4, "smoke": 8, "parity": 30}[suite]
    if environment == "linux-cuda":
        base = base // 2 + 1
    if executor == "hf_jobs":
        base += 5
    return base


def matching_artifact(artifacts: list[dict], suite: str, environment: str, executor: str) -> dict | None:
    suffix = f"-hf-jobs-{suite}" if executor == "hf_jobs" else f"-{environment}-{suite}"
    for item in artifacts:
        if str(item.get("name", "")).endswith(suffix):
            return item
    return None


def selected_job_name(executor: str, environment: str) -> str:
    if executor == "hf_jobs":
        return "Hugging Face Jobs"
    return {
        "linux-cpu": "GitHub / Linux CPU",
        "linux-cuda": "GitHub / Linux CUDA",
        "macos-coreml": "GitHub / macOS CoreML",
        "windows-directml": "GitHub / Windows DirectML",
    }[environment]


def artifact_provenance(artifact: dict, token: str) -> dict:
    url = str(artifact.get("archive_download_url") or "")
    if not url:
        return {}
    try:
        archive = zipfile.ZipFile(io.BytesIO(api_bytes(url, token)))
        candidates = [name for name in archive.namelist() if name.endswith("evaluation-provenance.json")]
        if not candidates:
            return {}
        with archive.open(candidates[0]) as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
        return {}


def cohort_samples(
    samples: list[dict],
    *,
    source_repository: str,
    hf_bucket: str,
    dataset_source: str,
    dataset_id: str,
) -> tuple[str, list[dict]]:
    if not samples:
        return "none", []

    def exact(sample: dict) -> bool:
        provenance = sample.get("provenance") or {}
        if source_repository and provenance.get("source_repository") != source_repository:
            return False
        if dataset_source and provenance.get("dataset_source") != dataset_source:
            return False
        if dataset_source == "bucket" and hf_bucket:
            return provenance.get("hf_bucket") == hf_bucket
        if dataset_source in {"repository", "custom"} and dataset_id:
            return provenance.get("dataset_id") == dataset_id
        return bool(source_repository or dataset_source)

    exact_values = [sample for sample in samples if exact(sample)]
    if len(exact_values) >= 3:
        return "exact-source-dataset", exact_values

    if source_repository:
        source_values = [
            sample
            for sample in samples
            if (sample.get("provenance") or {}).get("source_repository") == source_repository
        ]
        if len(source_values) >= 3:
            return "source-repository", source_values

    return "global", samples


def median_metric(samples: list[dict], key: str) -> int | None:
    values = []
    for sample in samples:
        value = (sample.get("provenance") or {}).get(key)
        if isinstance(value, int) and value > 0:
            values.append(value)
    if not values:
        return None
    return int(statistics.median(values))


def size_ratio(target_bytes: int | None, observed_bytes: int | None) -> float | None:
    if target_bytes is None or observed_bytes is None or target_bytes <= 0 or observed_bytes <= 0:
        return None
    return round(target_bytes / observed_bytes, 4)


def optional_positive_int(value: str | None, name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except ValueError as error:
        raise SystemExit(f"{name} must be a positive integer") from error
    if parsed <= 0:
        raise SystemExit(f"{name} must be a positive integer")
    return parsed


def workload_auto_enabled() -> bool:
    return (
        os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
        or os.environ.get("ENABLE_WORKLOAD_PROBE", "").lower() == "true"
    )


def helper_json(command: list[str], label: str) -> dict:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit={completed.returncode}"
        return {
            "method": "unavailable",
            "warning": f"{label}: {detail}".replace("\n", " "),
        }
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"method": "unavailable", "warning": f"{label} returned invalid JSON"}
    if not isinstance(value, dict):
        return {"method": "unavailable", "warning": f"{label} returned non-object JSON"}
    return value


def auto_candidate_workload(hf_bucket: str) -> dict:
    if not hf_bucket or not workload_auto_enabled():
        return {"method": "none"}
    request_path = Path(os.environ.get("CANDIDATE_REQUEST_JSON", "/tmp/request.json"))
    config_path = Path(os.environ.get("CANDIDATE_SOURCE_CONFIG_JSON", "/tmp/source.json"))
    if not request_path.is_file():
        return {"method": "none"}

    probe = Path(__file__).with_name("measure-candidate-bucket-size.py")
    command = [
        sys.executable,
        str(probe),
        "--bucket",
        hf_bucket,
        "--request-json",
        str(request_path),
        "--allow-unavailable",
    ]
    if config_path.is_file():
        command.extend(["--config-json", str(config_path)])
    value = helper_json(command, "candidate workload probe")
    if value.get("method") == "unavailable":
        return value
    if value.get("available") is not True:
        return {
            "method": "unavailable",
            "warning": str(value.get("warning") or "candidate workload unavailable"),
        }
    candidate_id = value.get("candidate_id")
    candidate_bytes = value.get("candidate_bytes")
    candidate_files = value.get("candidate_files")
    if (
        not isinstance(candidate_id, str)
        or not isinstance(candidate_bytes, int)
        or candidate_bytes <= 0
        or not isinstance(candidate_files, int)
        or candidate_files <= 0
    ):
        return {
            "method": "unavailable",
            "warning": "candidate workload probe returned invalid size evidence",
        }
    return {
        "method": "metadata-only",
        "candidate_id": candidate_id,
        "candidate_bytes": candidate_bytes,
        "candidate_files": candidate_files,
        "legacy_candidate_layout": value.get("legacy_candidate_layout"),
    }


def auto_dataset_workload(hf_bucket: str, dataset_source: str, dataset_id: str) -> dict:
    if not workload_auto_enabled() or dataset_source not in {
        "bucket",
        "repository",
        "custom",
    }:
        return {"method": "none"}
    probe = Path(__file__).with_name("measure-dataset-source-size.py")
    command = [
        sys.executable,
        str(probe),
        "--source",
        dataset_source,
        "--allow-unavailable",
    ]
    if dataset_source == "bucket":
        if not hf_bucket:
            return {"method": "none"}
        command.extend(["--bucket", hf_bucket])
    else:
        if not dataset_id:
            return {"method": "none"}
        command.extend(["--dataset-id", dataset_id])
    value = helper_json(command, "dataset workload probe")
    if value.get("method") == "unavailable":
        return value
    if value.get("available") is not True:
        return {
            "method": "unavailable",
            "warning": str(value.get("warning") or "dataset workload unavailable"),
        }
    dataset_bytes = value.get("dataset_bytes")
    dataset_files = value.get("dataset_files")
    if (
        not isinstance(dataset_bytes, int)
        or dataset_bytes <= 0
        or not isinstance(dataset_files, int)
        or dataset_files <= 0
    ):
        return {
            "method": "unavailable",
            "warning": "dataset workload probe returned invalid size evidence",
        }
    return {
        "method": "metadata-only",
        "dataset_bytes": dataset_bytes,
        "dataset_files": dataset_files,
        "probe_method": value.get("probe_method"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--suite", choices=["probe", "smoke", "parity"], required=True)
    parser.add_argument("--executor", choices=["github", "hf_jobs"], required=True)
    parser.add_argument(
        "--environment",
        choices=["linux-cpu", "linux-cuda", "macos-coreml", "windows-directml"],
        required=True,
    )
    parser.add_argument("--source-repository", default=os.environ.get("SOURCE_REPOSITORY", ""))
    parser.add_argument("--hf-bucket", default=os.environ.get("HF_BUCKET", ""))
    parser.add_argument("--dataset-source", default=os.environ.get("DATASET_SOURCE", ""))
    parser.add_argument("--dataset-id", default=os.environ.get("DATASET_ID", ""))
    parser.add_argument(
        "--target-candidate-bytes",
        default=os.environ.get("TARGET_CANDIDATE_BYTES", ""),
        help="Metadata-only size of the concrete candidate. Evidence only; does not scale estimate.",
    )
    parser.add_argument(
        "--target-dataset-bytes",
        default=os.environ.get("TARGET_DATASET_BYTES", ""),
        help="Metadata-only size of the selected dataset source. Evidence only; does not scale estimate.",
    )
    parser.add_argument("--workflow", default="candidate-package-evaluate-v2.yml")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--github-output")
    args = parser.parse_args()

    target_candidate_bytes = optional_positive_int(args.target_candidate_bytes, "target_candidate_bytes")
    candidate_workload = {"method": "explicit" if target_candidate_bytes is not None else "none"}
    if target_candidate_bytes is None:
        candidate_workload = auto_candidate_workload(args.hf_bucket)
        probed_bytes = candidate_workload.get("candidate_bytes")
        if isinstance(probed_bytes, int) and probed_bytes > 0:
            target_candidate_bytes = probed_bytes

    target_dataset_bytes = optional_positive_int(args.target_dataset_bytes, "target_dataset_bytes")
    dataset_workload = {"method": "explicit" if target_dataset_bytes is not None else "none"}
    if target_dataset_bytes is None:
        dataset_workload = auto_dataset_workload(args.hf_bucket, args.dataset_source, args.dataset_id)
        probed_dataset_bytes = dataset_workload.get("dataset_bytes")
        if isinstance(probed_dataset_bytes, int) and probed_dataset_bytes > 0:
            target_dataset_bytes = probed_dataset_bytes

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    fallback = fallback_minutes(args.suite, args.executor, args.environment)
    result = {
        "schema_version": 5,
        "method": "fallback",
        "cohort": "none",
        "samples": 0,
        "available_samples": 0,
        "estimate_minutes": fallback,
        "p50_minutes": None,
        "p90_minutes": None,
        "suite": args.suite,
        "executor": args.executor,
        "environment": args.environment,
        "source_repository": args.source_repository,
        "hf_bucket": args.hf_bucket,
        "dataset_source": args.dataset_source,
        "dataset_id": args.dataset_id,
        "workload_probe_method": candidate_workload.get("method", "none"),
        "workload_warning": candidate_workload.get("warning"),
        "target_candidate_id": candidate_workload.get("candidate_id"),
        "target_candidate_bytes": target_candidate_bytes,
        "target_candidate_files": candidate_workload.get("candidate_files"),
        "target_candidate_legacy_layout": candidate_workload.get("legacy_candidate_layout"),
        "dataset_workload_probe_method": dataset_workload.get("method", "none"),
        "dataset_workload_warning": dataset_workload.get("warning"),
        "target_dataset_bytes": target_dataset_bytes,
        "target_dataset_files": dataset_workload.get("dataset_files"),
        "observed_dataset_bytes_p50": None,
        "observed_package_bytes_p50": None,
        "observed_candidate_bytes_p50": None,
        "candidate_size_ratio_p50": None,
        "dataset_size_ratio_p50": None,
        "size_scaling_applied": False,
    }

    if token:
        base = f"https://api.github.com/repos/{args.repository}"
        try:
            runs = api_get(
                f"{base}/actions/workflows/{args.workflow}/runs?status=success&per_page={min(max(args.limit, 1), 100)}",
                token,
            ).get("workflow_runs", [])
            samples: list[dict] = []
            target_job = selected_job_name(args.executor, args.environment)
            for run in runs:
                run_id = run.get("id")
                if not run_id:
                    continue
                artifacts = api_get(f"{base}/actions/runs/{run_id}/artifacts?per_page=100", token).get("artifacts", [])
                artifact = matching_artifact(artifacts, args.suite, args.environment, args.executor)
                if artifact is None:
                    continue
                jobs = api_get(f"{base}/actions/runs/{run_id}/jobs?per_page=100", token).get("jobs", [])
                wanted = {
                    "Resolve request",
                    "Build digest-pinned candidate package",
                    target_job,
                }
                durations = [
                    duration_minutes(job)
                    for job in jobs
                    if job.get("name") in wanted and job.get("conclusion") == "success"
                ]
                durations = [value for value in durations if value is not None]
                if (
                    not any(job.get("name") == target_job and job.get("conclusion") == "success" for job in jobs)
                    or not durations
                ):
                    continue
                samples.append(
                    {
                        "minutes": sum(durations),
                        "provenance": artifact_provenance(artifact, token),
                    }
                )

            result["available_samples"] = len(samples)
            cohort, selected = cohort_samples(
                samples,
                source_repository=args.source_repository,
                hf_bucket=args.hf_bucket,
                dataset_source=args.dataset_source,
                dataset_id=args.dataset_id,
            )
            if selected:
                values = [float(sample["minutes"]) for sample in selected]
                p50 = statistics.median(values)
                p90 = percentile(values, 0.90)
                observed_candidate_bytes = median_metric(selected, "candidate_bytes")
                observed_dataset_bytes = median_metric(selected, "dataset_bytes")
                result.update(
                    method="historical",
                    cohort=cohort,
                    samples=len(values),
                    estimate_minutes=max(1, math.ceil(p90)),
                    p50_minutes=round(p50, 2),
                    p90_minutes=round(p90, 2),
                    observed_dataset_bytes_p50=observed_dataset_bytes,
                    observed_package_bytes_p50=median_metric(selected, "package_bytes"),
                    observed_candidate_bytes_p50=observed_candidate_bytes,
                    candidate_size_ratio_p50=size_ratio(target_candidate_bytes, observed_candidate_bytes),
                    dataset_size_ratio_p50=size_ratio(target_dataset_bytes, observed_dataset_bytes),
                )
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
        ) as error:
            result["warning"] = f"history unavailable: {error}"

    print(json.dumps(result, ensure_ascii=False))
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            for key in (
                "method",
                "cohort",
                "samples",
                "available_samples",
                "estimate_minutes",
                "p50_minutes",
                "p90_minutes",
                "workload_probe_method",
                "workload_warning",
                "target_candidate_id",
                "target_candidate_bytes",
                "target_candidate_files",
                "target_candidate_legacy_layout",
                "dataset_workload_probe_method",
                "dataset_workload_warning",
                "target_dataset_bytes",
                "target_dataset_files",
                "observed_dataset_bytes_p50",
                "observed_package_bytes_p50",
                "observed_candidate_bytes_p50",
                "candidate_size_ratio_p50",
                "dataset_size_ratio_p50",
                "size_scaling_applied",
            ):
                value = result[key]
                if isinstance(value, bool):
                    rendered = "true" if value else "false"
                else:
                    rendered = "" if value is None else str(value).replace("\n", " ")
                handle.write(f"{key}={rendered}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
