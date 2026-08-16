from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import soundfile as sf
import torch
from huggingface_hub import hf_hub_download
from scipy.signal import resample_poly
from transformers import AutoModelForCTC, AutoProcessor

MODEL_ID = os.environ.get("CTC_MODEL_ID", "TKU410410103/wav2vec2-base-japanese-asr")
DATASET_ID = "japanese-asr/ja_asr.jsut_basic5000"
TARGET_SAMPLE_RATE = 16_000
OUT = Path(os.environ.get("CTC_E2E_OUT", ".ci/public-model-e2e/ctc"))
OUT.mkdir(parents=True, exist_ok=True)

sample_path = Path(hf_hub_download(DATASET_ID, "sample.flac", repo_type="dataset"))
audio, source_sample_rate = sf.read(sample_path, dtype="float32", always_2d=False)
if audio.ndim == 2:
    audio = audio.mean(axis=1)
if audio.size == 0 or not np.isfinite(audio).all():
    raise RuntimeError("JSUT sample is empty or non-finite")

if source_sample_rate != TARGET_SAMPLE_RATE:
    divisor = math.gcd(source_sample_rate, TARGET_SAMPLE_RATE)
    audio = resample_poly(
        audio,
        TARGET_SAMPLE_RATE // divisor,
        source_sample_rate // divisor,
    ).astype(np.float32, copy=False)
if audio.size == 0 or not np.isfinite(audio).all():
    raise RuntimeError("resampled JSUT sample is empty or non-finite")

processor = AutoProcessor.from_pretrained(MODEL_ID)
model = AutoModelForCTC.from_pretrained(MODEL_ID).eval()
inputs = processor(audio, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt")
input_values = inputs.input_values

with torch.inference_mode():
    torch_logits = model(input_values=input_values).logits.cpu().numpy()


class LogitsOnly(torch.nn.Module):
    def __init__(self, inner: torch.nn.Module) -> None:
        super().__init__()
        self.inner = inner

    def forward(self, input_values: torch.Tensor) -> torch.Tensor:
        return self.inner(input_values=input_values).logits


onnx_path = OUT / "model.onnx"
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

session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
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

max_abs = float(np.max(np.abs(torch_logits - ort_logits)))
blank_id = int(model.config.pad_token_id)
summary = {
    "model_id": MODEL_ID,
    "dataset_id": DATASET_ID,
    "sample_file": "sample.flac",
    "source_sample_rate_hz": source_sample_rate,
    "sample_rate_hz": TARGET_SAMPLE_RATE,
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
}
(OUT / "result.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
