#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()

    raw = "".join(sys.stdin.read().split())
    if not raw:
        raise SystemExit("GitHub content payload is empty")
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise SystemExit(f"GitHub content payload is not valid base64: {error}") from error

    if args.output:
        with open(args.output, "wb") as handle:
            handle.write(decoded)
    else:
        sys.stdout.buffer.write(decoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
