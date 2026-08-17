#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import math
import os
import statistics
import urllib.error
import urllib.request
import zipfile
from datetime import datetime


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
    with urllib.request.urlopen(
        request(url, token, accept="application/vnd.github+json"), timeout=30
    ) as response:
        return json.load(response)


def api_bytes(url: str, token: str) -> bytes:
    with urllib.request.urlopen(
        request(url, token, accept="application/vnd.github+json"), timeout=30
    ) as response:
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


def matching_artifact(artifacts: list[dict], suite: str, environment: str) -> dict | None:
    suffix = f"-{environment}-{suite}"
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
        candidates = [
            name
            for name in archive.namelist()
            if name.endswith("evaluation-provenance.json")
        ]
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
            if (sample.get("provenance") or {}).get("source_repository")
            == source_repository
        ]
        if len(source_values) >= 3:
            return "source-repository", source_values

    return "global", samples


def median_metric(samples: list[dict], key: str) -> int | None:
    values = []
    for sample in samples:
        value = (sample.get("provenance") or {}).get(key)
        if isinstance(value, int) and value >= 0:
            values.append(value)
    if not values:
        return None
    return int(statistics.median(values))


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
    parser.add_argument("--workflow", default="candidate-package-evaluate.yml")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--github-output")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    fallback = fallback_minutes(args.suite, args.executor, args.environment)
    result = {
        "schema_version": 2,
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
        "observed_dataset_bytes_p50": None,
        "observed_package_bytes_p50": None,
        "observed_candidate_bytes_p50": None,
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
                artifacts = api_get(
                    f"{base}/actions/runs/{run_id}/artifacts?per_page=100", token
                ).get("artifacts", [])
                artifact = None
                if args.executor == "github":
                    artifact = matching_artifact(artifacts, args.suite, args.environment)
                    if artifact is None:
                        continue
                jobs = api_get(
                    f"{base}/actions/runs/{run_id}/jobs?per_page=100", token
                ).get("jobs", [])
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
                if not any(
                    job.get("name") == target_job and job.get("conclusion") == "success"
                    for job in jobs
                ) or not durations:
                    continue
                samples.append(
                    {
                        "minutes": sum(durations),
                        "provenance": artifact_provenance(artifact, token)
                        if artifact is not None
                        else {},
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
                result.update(
                    method="historical",
                    cohort=cohort,
                    samples=len(values),
                    estimate_minutes=max(1, math.ceil(p90)),
                    p50_minutes=round(p50, 2),
                    p90_minutes=round(p90, 2),
                    observed_dataset_bytes_p50=median_metric(
                        selected, "dataset_bytes"
                    ),
                    observed_package_bytes_p50=median_metric(
                        selected, "package_bytes"
                    ),
                    observed_candidate_bytes_p50=median_metric(
                        selected, "candidate_bytes"
                    ),
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
                "observed_dataset_bytes_p50",
                "observed_package_bytes_p50",
                "observed_candidate_bytes_p50",
            ):
                value = result[key]
                handle.write(f"{key}={'' if value is None else value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
