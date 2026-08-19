#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Callable, ContextManager, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class Response(Protocol):
    status: int

    def read(self) -> bytes: ...


Opener = Callable[..., ContextManager[Response]]


def validate_repository(value: str) -> str:
    if not REPOSITORY_RE.fullmatch(value):
        raise ValueError("repository must use canonical owner/name format")
    owner, name = value.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError("repository must not contain dot-only path segments")
    return value


def validate_content_path(value: str) -> str:
    if not value or value.startswith("/") or value.endswith("/") or "\\" in value:
        raise ValueError("content path must be a safe relative path")
    parts = value.split("/")
    if any(
        part in {"", ".", ".."} or not PATH_SEGMENT_RE.fullmatch(part)
        for part in parts
    ):
        raise ValueError("content path contains an unsafe path segment")
    return value


def validate_ref(value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError("ref must be an immutable lowercase 40-hex commit SHA")
    return value


def build_url(api_url: str, repository: str, path: str, ref: str = "") -> str:
    repository = validate_repository(repository)
    path = validate_content_path(path)
    if ref:
        ref = validate_ref(ref)
    owner, name = repository.split("/", 1)
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
    url = (
        f"{api_url.rstrip('/')}/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        f"/contents/{encoded_path}"
    )
    if ref:
        url = f"{url}?{urlencode({'ref': ref})}"
    return url


def fetch_content_sha(
    repository: str,
    path: str,
    token: str,
    *,
    ref: str = "",
    api_url: str = "https://api.github.com",
    opener: Opener = urlopen,
) -> str | None:
    if not token:
        raise ValueError("GH_TOKEN is required")
    url = build_url(api_url, repository, path, ref)
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "jpapt-bootstrap-content-reader",
        },
        method="GET",
    )
    try:
        with opener(request, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"GitHub Contents lookup returned unexpected HTTP {response.status}"
                )
            raw = response.read()
    except HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError(
            f"GitHub Contents lookup failed with HTTP {error.code}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"GitHub Contents lookup transport failure: {error}") from error

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("GitHub Contents lookup returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("GitHub Contents lookup must return a JSON object")
    sha = value.get("sha")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise RuntimeError("GitHub Contents lookup returned an invalid content SHA")
    return sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--ref", default="")
    args = parser.parse_args()
    try:
        sha = fetch_content_sha(
            args.repository,
            args.path,
            os.environ.get("GH_TOKEN", ""),
            ref=args.ref,
            api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        )
    except (ValueError, RuntimeError) as error:
        print(f"GitHub content metadata lookup rejected: {error}", file=sys.stderr)
        return 2
    print("missing" if sha is None else sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
