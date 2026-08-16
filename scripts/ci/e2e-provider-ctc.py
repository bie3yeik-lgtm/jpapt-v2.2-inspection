from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import wave
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_model(path: Path) -> None:
    input_value = helper.make_tensor_value_info(
        "input_values", TensorProto.FLOAT, [1, "samples"]
    )
    output_value = helper.make_tensor_value_info(
        "logits", TensorProto.FLOAT, [1, "samples", 3]
    )
    axes = helper.make_tensor("axes", TensorProto.INT64, [1], [2])
    zero = helper.make_tensor("zero", TensorProto.FLOAT, [], [0.0])
    one = helper.make_tensor("one", TensorProto.FLOAT, [], [1.0])
    graph = helper.make_graph(
        [
            helper.make_node("Unsqueeze", ["input_values", "axes"], ["x3"]),
            helper.make_node("Mul", ["x3", "zero"], ["zeros"]),
            helper.make_node("Add", ["zeros", "one"], ["token_a"]),
            helper.make_node(
                "Concat", ["token_a", "zeros", "zeros"], ["logits"], axis=2
            ),
        ],
        "strict-provider-ctc-probe",
        [input_value],
        [output_value],
        [axes, zero, one],
    )
    model = helper.make_model(
        graph,
        producer_name="jpapt-provider-probe",
        opset_imports=[helper.make_opsetid("", 17)],
    )
    model.ir_version = 10
    onnx.checker.check_model(model)
    onnx.save(model, path)


def build_wav(path: Path) -> None:
    sample_rate = 16_000
    frames = 1_600
    samples = [
        int(0.1 * 32767 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
        for i in range(frames)
    ]
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))


def build_fixture(output: Path) -> None:
    candidate = output / "candidate"
    tokenizer = candidate / "tokenizer"
    tokenizer.mkdir(parents=True, exist_ok=True)

    model_path = candidate / "model.onnx"
    build_model(model_path)
    (candidate / "config.json").write_text(
        json.dumps({"blank_id": 2}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (candidate / "metadata.json").write_text(
        json.dumps(
            {
                "profile_set": "parakeet-tdt-ctc-v1",
                "variants": {
                    "ctc": {
                        "artifacts": {"primary": "model.onnx"},
                        "tokenizer": "tokenizer/vocabulary.json",
                    }
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (candidate / ".candidate-id").write_text(
        "strict-provider-ctc-probe\n", encoding="utf-8"
    )
    (tokenizer / "vocabulary.json").write_text(
        json.dumps(["a", "b", "<blank>"], indent=2) + "\n",
        encoding="utf-8",
    )

    audio_path = output / "probe.wav"
    build_wav(audio_path)
    audio_sha = sha256_file(audio_path)
    manifest = {
        "schema_version": 1,
        "manifest_path": "provider-probe:synthetic-ctc",
        "expected_sample_count": 1,
        "resolved_sample_count": 1,
        "samples": [
            {
                "id": "provider-probe",
                "manifest_entry_id": "provider-probe",
                "dataset_id": "provider-probe",
                "dataset_repo_id": None,
                "dataset_revision": None,
                "subset": None,
                "split": None,
                "row_index": 0,
                "source_identity": "generated:provider-probe.wav",
                "selection_hash": audio_sha,
                "selection_rank": 0,
                "duration_sec": 0.1,
                "sample_rate_hz": 16000,
                "transcription": "a",
                "tags": ["synthetic", "provider-probe"],
                "audio_path": str(audio_path.resolve()),
                "audio_sha256": audio_sha,
            }
        ],
    }
    (output / "resolved-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "candidate_dir": str(candidate.resolve()),
                "model_sha256": sha256_file(model_path),
                "model_size_bytes": model_path.stat().st_size,
                "audio_sha256": audio_sha,
            },
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    build_fixture(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
