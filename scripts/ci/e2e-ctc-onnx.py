from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

import numpy as np
import onnx
import onnxruntime as ort
from scipy.signal import resample_poly
import soundfile as sf
import torch
from huggingface_hub import hf_hub_download
from transformers import AutoModelForCTC, AutoProcessor

MODEL_ID = os.environ.get("CTC_MODEL_ID", "TKU410410103/wav2vec2-base-japanese-asr")
DATASET_ID = "japanese-asr/ja_asr.jsut_basic5000"
REFERENCE_TEXT = "水をマレーシアから買わなくてはならないのです"
OUT = Path(os.environ.get("CTC_E2E_OUT", ".ci/public-model-e2e/ctc"))
CANDIDATE = OUT / "candidate"
TOKENIZER = CANDIDATE / "tokenizer"
OUT.mkdir(parents=True, exist_ok=True)
TOKENIZER.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


sample_path = Path(hf_hub_download(DATASET_ID, "sample.flac", repo_type="dataset"))
audio, source_sample_rate = sf.read(sample_path, dtype="float32", always_2d=False)
if audio.ndim == 2:
    audio = audio.mean(axis=1)
if audio.size == 0 or not np.isfinite(audio).all():
    raise RuntimeError("JSUT sample is empty or non-finite")
source_sample_count = int(audio.size)
source_duration_sec = float(audio.size / source_sample_rate)
if source_sample_rate != 16_000:
    divisor = int(np.gcd(source_sample_rate, 16_000))
    audio = resample_poly(audio, 16_000 // divisor, source_sample_rate // divisor).astype(
        np.float32,
        copy=False,
    )
sample_rate = 16_000
if audio.size == 0 or not np.isfinite(audio).all():
    raise RuntimeError("resampled JSUT sample is empty or non-finite")

processor = AutoProcessor.from_pretrained(MODEL_ID)
model = AutoModelForCTC.from_pretrained(MODEL_ID).eval()
inputs = processor(audio, sampling_rate=sample_rate, return_tensors="pt")
input_values = inputs.input_values

with torch.inference_mode():
    torch_logits = model(input_values=input_values).logits.cpu().numpy()


class LogitsOnly(torch.nn.Module):
    def __init__(self, inner: torch.nn.Module) -> None:
        super().__init__()
        self.inner = inner

    def forward(self, input_values: torch.Tensor) -> torch.Tensor:
        return self.inner(input_values=input_values).logits


onnx_path = CANDIDATE / "model.onnx"
torch.onnx.export(
    LogitsOnly(model),
    (input_values,),
    onnx_path,
    input_names=["input_values"],
    output_names=["logits"],
    dynamic_axes={
        "input_values": {1: "samples"},
        "logits": {1: "frames"},
    },
    opset_version=17,
    do_constant_folding=True,
    dynamo=False,
)
onnx.checker.check_model(onnx.load(onnx_path, load_external_data=False))

session = ort.InferenceSession(
    str(onnx_path),
    providers=["CPUExecutionProvider"],
)
ort_logits = session.run(
    ["logits"],
    {"input_values": input_values.cpu().numpy()},
)[0]
if ort_logits.shape != torch_logits.shape:
    raise RuntimeError(
        f"ONNX logits shape mismatch: torch={torch_logits.shape}, ort={ort_logits.shape}"
    )
if not np.isfinite(ort_logits).all():
    raise RuntimeError("ONNX logits contain NaN or Inf")

pt_ids = np.argmax(torch_logits, axis=-1)
ort_ids = np.argmax(ort_logits, axis=-1)
pt_text = processor.batch_decode(pt_ids)[0].strip()
ort_text = processor.batch_decode(ort_ids)[0].strip()
if not ort_text:
    raise RuntimeError("ONNX CTC transcript is empty")
if pt_text != ort_text:
    raise RuntimeError(
        f"PyTorch/ONNX transcript mismatch: torch={pt_text!r}, ort={ort_text!r}"
    )

blank_id = int(model.config.pad_token_id)
raw_vocab = processor.tokenizer.get_vocab()
id_to_token: dict[str, str] = {}
for token, index in raw_vocab.items():
    rendered = " " if token == processor.tokenizer.word_delimiter_token else token
    id_to_token[str(int(index))] = rendered

vocabulary_path = TOKENIZER / "vocabulary.json"
vocabulary_path.write_text(
    json.dumps(id_to_token, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
(CANDIDATE / "config.json").write_text(
    json.dumps(
        {"blank_id": blank_id, "pad_token_id": blank_id},
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
(CANDIDATE / "metadata.json").write_text(
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
(CANDIDATE / ".candidate-id").write_text("public-wav2vec2-japanese-ctc\n", encoding="utf-8")

materialized_audio = OUT / "sample.flac"
shutil.copyfile(sample_path, materialized_audio)
selection_hash = sha256_file(materialized_audio)
resolved_manifest = {
    "schema_version": 1,
    "manifest_path": "public-model-e2e:jsut-sample.flac",
    "expected_sample_count": 1,
    "resolved_sample_count": 1,
    "samples": [
        {
            "id": "jsut-sample",
            "manifest_entry_id": "jsut-sample",
            "dataset_id": "jsut-basic5000",
            "dataset_repo_id": DATASET_ID,
            "dataset_revision": "main",
            "subset": None,
            "split": None,
            "row_index": 0,
            "source_identity": f"{DATASET_ID}:sample.flac",
            "selection_hash": selection_hash,
            "selection_rank": 0,
            "duration_sec": source_duration_sec,
            "sample_rate_hz": int(source_sample_rate),
            "transcription": REFERENCE_TEXT,
            "tags": ["public-model-e2e", "jsut"],
            "audio_path": str(materialized_audio.resolve()),
            "audio_sha256": selection_hash,
        }
    ],
}
(OUT / "resolved-manifest.json").write_text(
    json.dumps(resolved_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

max_abs = float(np.max(np.abs(torch_logits - ort_logits)))
summary = {
    "model_id": MODEL_ID,
    "dataset_id": DATASET_ID,
    "sample_file": "sample.flac",
    "source_sample_rate_hz": int(source_sample_rate),
    "source_sample_count": source_sample_count,
    "sample_rate_hz": sample_rate,
    "sample_count": int(audio.size),
    "onnx_opset": 17,
    "onnxruntime_version": ort.__version__,
    "input_names": [item.name for item in session.get_inputs()],
    "output_names": [item.name for item in session.get_outputs()],
    "blank_id": blank_id,
    "torch_transcript": pt_text,
    "onnx_transcript": ort_text,
    "transcript_parity": True,
    "max_abs_logit_error": max_abs,
    "candidate_dir": str(CANDIDATE.resolve()),
    "resolved_manifest": str((OUT / "resolved-manifest.json").resolve()),
}
(OUT / "result.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
