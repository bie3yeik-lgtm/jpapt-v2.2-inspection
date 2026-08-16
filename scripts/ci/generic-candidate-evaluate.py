#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort


def tensor_cases(dataset_dir: Path):
    if not dataset_dir.exists():
        return []
    return sorted(dataset_dir.rglob("*.npz"))


def load_case(path: Path):
    data = np.load(path, allow_pickle=False)
    inputs = {k.removeprefix("input__"): data[k] for k in data.files if k.startswith("input__")}
    outputs = {k.removeprefix("output__"): data[k] for k in data.files if k.startswith("output__")}
    return inputs, outputs


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate-dir", default="/opt/jpapt/candidate")
    p.add_argument("--dataset-dir", default="/data")
    p.add_argument("--suite", choices=["smoke", "parity", "probe"], default="smoke")
    p.add_argument("--provider", default="CPUExecutionProvider")
    p.add_argument("--output", default="/results/result.json")
    p.add_argument("--atol", type=float, default=1e-4)
    p.add_argument("--rtol", type=float, default=1e-3)
    args = p.parse_args()

    candidate = Path(args.candidate_dir)
    dataset = Path(args.dataset_dir)
    models = sorted(candidate.rglob("*.onnx"))
    if not models:
        raise SystemExit(f"no ONNX models under {candidate}")

    available = ort.get_available_providers()
    provider = args.provider if args.provider in available else "CPUExecutionProvider"
    report = {
        "schema_version": 1,
        "suite": args.suite,
        "requested_provider": args.provider,
        "provider": provider,
        "available_providers": available,
        "models": [],
        "cases": [],
        "passed": True,
    }

    sessions = []
    for model in models:
        started = time.perf_counter()
        sess = ort.InferenceSession(str(model), providers=[provider])
        elapsed = time.perf_counter() - started
        sessions.append((model, sess))
        report["models"].append({
            "path": str(model.relative_to(candidate)),
            "load_seconds": elapsed,
            "inputs": [{"name": x.name, "shape": x.shape, "type": x.type} for x in sess.get_inputs()],
            "outputs": [{"name": x.name, "shape": x.shape, "type": x.type} for x in sess.get_outputs()],
        })

    cases = tensor_cases(dataset)
    if args.suite == "probe":
        pass
    elif args.suite == "smoke":
        if cases:
            inputs, _ = load_case(cases[0])
            model, sess = sessions[0]
            started = time.perf_counter()
            outputs = sess.run(None, inputs)
            report["cases"].append({
                "case": str(cases[0]),
                "model": str(model.relative_to(candidate)),
                "elapsed_seconds": time.perf_counter() - started,
                "output_count": len(outputs),
                "passed": True,
            })
        else:
            report["cases"].append({"case": None, "passed": True, "note": "structural smoke: no .npz case supplied"})
    else:
        if not cases:
            raise SystemExit("parity requires at least one .npz case in dataset-dir")
        model, sess = sessions[0]
        output_names = [x.name for x in sess.get_outputs()]
        for case in cases:
            inputs, expected = load_case(case)
            if not inputs or not expected:
                raise SystemExit(f"parity case must contain input__* and output__*: {case}")
            actual_values = sess.run(output_names, inputs)
            actual = dict(zip(output_names, actual_values))
            checks = []
            passed = True
            for name, exp in expected.items():
                if name not in actual:
                    checks.append({"output": name, "passed": False, "reason": "missing output"})
                    passed = False
                    continue
                ok = bool(np.allclose(actual[name], exp, atol=args.atol, rtol=args.rtol, equal_nan=True))
                max_abs = float(np.max(np.abs(actual[name] - exp))) if actual[name].size else 0.0
                checks.append({"output": name, "passed": ok, "max_abs": max_abs})
                passed &= ok
            report["cases"].append({"case": str(case), "passed": passed, "checks": checks})
            report["passed"] &= passed

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
