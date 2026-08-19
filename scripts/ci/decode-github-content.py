#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import sys


def decode_payload(payload: str) -> bytes:
    if not payload:
        raise SystemExit("GitHub content payload is empty")

    compact = "".join(payload.split())
    try:
        return base64.b64decode(compact, validate=True)
    except (ValueError, binascii.Error):
        # `gh api --jq .content` has produced both GitHub's base64 field and
        # already-decoded/raw text across client/API paths. Treat a non-base64
        # payload as raw UTF-8 bytes; callers still validate schema/content or
        # compare its SHA-256 against an immutable manifest before accepting it.
        return payload.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()

    decoded = decode_payload(sys.stdin.read())
    if args.output:
        with open(args.output, "wb") as handle:
            handle.write(decoded)
    else:
        sys.stdout.buffer.write(decoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
