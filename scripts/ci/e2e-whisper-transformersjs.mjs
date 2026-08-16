import { pipeline, read_audio } from "@huggingface/transformers";

const MODEL_ID = process.env.WHISPER_MODEL_ID ?? "onnx-community/whisper-small";
const AUDIO_URL =
  process.env.JSUT_SAMPLE_URL ??
  "https://huggingface.co/datasets/japanese-asr/ja_asr.jsut_basic5000/resolve/main/sample.flac";

const transcriber = await pipeline("automatic-speech-recognition", MODEL_ID, {
  dtype: "q8",
});
const audio = await read_audio(AUDIO_URL, 16_000);
if (!(audio instanceof Float32Array) || audio.length === 0) {
  throw new Error("JSUT sample did not decode to a non-empty Float32Array");
}
if (!audio.every(Number.isFinite)) {
  throw new Error("JSUT sample contains non-finite audio samples");
}

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
      sample_url: AUDIO_URL,
      sample_count: audio.length,
      transcript: text,
      backend: "Transformers.js/ONNX Runtime",
      dtype: "q8",
    },
    null,
    2,
  ),
);
