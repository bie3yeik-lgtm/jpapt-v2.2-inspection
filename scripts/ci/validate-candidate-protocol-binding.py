#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--receipt")
    source.add_argument("--rejection")
    parser.add_argument("--ack")
    parser.add_argument("--receiver-repository")
    parser.add_argument("--orchestrator-repository")
    parser.add_argument("--allowed-orchestrators", default="")
    args = parser.parse_args()

    command = [
        "cargo",
        "run",
        "--quiet",
        "--locked",
        "-p",
        "asr-contracts",
        "--bin",
        "asr-candidate-protocol",
        "--",
    ]
    if args.rejection:
        if args.ack:
            parser.error("--ack cannot be combined with --rejection")
        if not args.receiver_repository:
            parser.error("--receiver-repository is required with --rejection")
        command.extend(
            [
                "receiver-binding",
                "--kind",
                "rejection",
                "--input",
                args.rejection,
                "--receiver",
                args.receiver_repository,
                "--allowed",
                args.allowed_orchestrators,
            ]
        )
    elif args.ack:
        if not args.orchestrator_repository:
            parser.error("--orchestrator-repository is required with --ack")
        command.extend(
            [
                "ack-binding",
                "--receipt",
                args.receipt,
                "--ack",
                args.ack,
                "--orchestrator",
                args.orchestrator_repository,
            ]
        )
    else:
        if not args.receiver_repository:
            parser.error("--receiver-repository is required without --ack")
        command.extend(
            [
                "receiver-binding",
                "--kind",
                "receipt",
                "--input",
                args.receipt,
                "--receiver",
                args.receiver_repository,
                "--allowed",
                args.allowed_orchestrators,
            ]
        )

    os.execvp(command[0], command)
    raise AssertionError("os.execvp returned unexpectedly")


if __name__ == "__main__":
    raise SystemExit(main())
