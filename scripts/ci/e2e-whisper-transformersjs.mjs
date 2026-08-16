import fs from "node:fs";
import { pipeline } from "@huggingface/transformers";

const MODEL_ID = process.env.WHISPER_MODEL_ID ?? "onnx-community/whisper-small";
const AUDIO_PATH = process.env.JSUT_PCM_PATH ?? ".ci/jsut-sample.f32";

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
