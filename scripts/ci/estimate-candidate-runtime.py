#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import urllib.error
import urllib.request
from datetime import datetime


def api_get(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "jpapt-runtime-estimator",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


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


def artifact_matches(artifacts: list[dict], suite: str, environment: str) -> bool:
    suffix = f"-{environment}-{suite}"
    return any(str(item.get("name", "")).endswith(suffix) for item in artifacts)


def selected_job_name(executor: str, environment: str) -> str:
    if executor == "hf_jobs":
        return "Hugging Face Jobs"
    return {
        "linux-cpu": "GitHub / Linux CPU",
        "linux-cuda": "GitHub / Linux CUDA",
        "macos-coreml": "GitHub / macOS CoreML",
        "windows-directml": "GitHub / Windows DirectML",
    }[environment]


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
    parser.add_argument("--workflow", default="candidate-package-evaluate.yml")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--github-output")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    fallback = fallback_minutes(args.suite, args.executor, args.environment)
    result = {
        "schema_version": 1,
        "method": "fallback",
        "samples": 0,
        "estimate_minutes": fallback,
        "p50_minutes": None,
        "p90_minutes": None,
        "suite": args.suite,
        "executor": args.executor,
        "environment": args.environment,
    }

    if token:
        base = f"https://api.github.com/repos/{args.repository}"
        try:
            runs = api_get(
                f"{base}/actions/workflows/{args.workflow}/runs?status=success&per_page={min(max(args.limit, 1), 100)}",
                token,
            ).get("workflow_runs", [])
            samples: list[float] = []
            target_job = selected_job_name(args.executor, args.environment)
            for run in runs:
                run_id = run.get("id")
                if not run_id:
                    continue
                artifacts = api_get(f"{base}/actions/runs/{run_id}/artifacts?per_page=100", token).get("artifacts", [])
                if args.executor == "github" and not artifact_matches(artifacts, args.suite, args.environment):
                    continue
                jobs = api_get(f"{base}/actions/runs/{run_id}/jobs?per_page=100", token).get("jobs", [])
                wanted = {
                    "Resolve request",
                    "Build digest-pinned candidate package",
                    target_job,
                }
                durations = [duration_minutes(job) for job in jobs if job.get("name") in wanted and job.get("conclusion") == "success"]
                durations = [value for value in durations if value is not None]
                if any(job.get("name") == target_job and job.get("conclusion") == "success" for job in jobs) and durations:
                    samples.append(sum(durations))
            if samples:
                p50 = statistics.median(samples)
                p90 = percentile(samples, 0.90)
                result.update(
                    method="historical",
                    samples=len(samples),
                    estimate_minutes=max(1, math.ceil(p90)),
                    p50_minutes=round(p50, 2),
                    p90_minutes=round(p90, 2),
                )
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
            result["warning"] = f"history unavailable: {error}"

    print(json.dumps(result, ensure_ascii=False))
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            for key in ("method", "samples", "estimate_minutes", "p50_minutes", "p90_minutes"):
                value = result[key]
                handle.write(f"{key}={'' if value is None else value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
