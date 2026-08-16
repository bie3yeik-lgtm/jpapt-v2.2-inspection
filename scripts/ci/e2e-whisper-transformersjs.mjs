import fs from "node:fs";
import { pipeline } from "@huggingface/transformers";

const MODEL_ID = process.env.WHISPER_MODEL_ID ?? "onnx-community/whisper-small";
const MODEL_REVISION = process.env.WHISPER_MODEL_REVISION;
const DATASET_ID = process.env.JSUT_DATASET_ID ?? "japanese-asr/ja_asr.jsut_basic5000";
const DATASET_REVISION = process.env.JSUT_DATASET_REVISION;
const SAMPLE_SHA256 = process.env.JSUT_SAMPLE_SHA256;
const AUDIO_PATH = process.env.JSUT_PCM_PATH ?? ".ci/jsut-sample.f32";

for (const [name, value] of [
  ["WHISPER_MODEL_REVISION", MODEL_REVISION],
  ["JSUT_DATASET_REVISION", DATASET_REVISION],
  ["JSUT_SAMPLE_SHA256", SAMPLE_SHA256],
]) {
  if (!value) {
    throw new Error(`${name} must be a concrete provenance value`);
  }
}

const raw = fs.readFileSync(AUDIO_PATH);
if (raw.byteLength === 0 || raw.byteLength % 4 !== 0) {
  throw new Error(`invalid float32 PCM byte length: ${raw.byteLength}`);
}
const audio = new Float32Array(
  raw.buffer,
  raw.byteOffset,
  Math.floor(raw.byteLength / Float32Array.BYTES_PER_ELEMENT),
);
if (audio.length === 0 || !audio.every(Number.isFinite)) {
  throw new Error("JSUT PCM is empty or contains non-finite samples");
}

const transcriber = await pipeline("automatic-speech-recognition", MODEL_ID, {
  dtype: "q8",
  revision: MODEL_REVISION,
});
const output = await transcriber(audio, {
  language: "japanese",
  task: "transcribe",
});
const text = output?.text?.trim?.() ?? "";
if (!text) {
  throw new Error(`Whisper ONNX returned an empty transcript: ${JSON.stringify(output)}`);
}

console.log(
  JSON.stringify(
    {
      model_id: MODEL_ID,
      model_revision: MODEL_REVISION,
      dataset_id: DATASET_ID,
      dataset_revision: DATASET_REVISION,
      sample_sha256: SAMPLE_SHA256,
      sample_path: AUDIO_PATH,
      sample_rate_hz: 16000,
      sample_count: audio.length,
      transcript: text,
      backend: "Transformers.js/ONNX Runtime",
      dtype: "q8",
    },
    null,
    2,
  ),
);
