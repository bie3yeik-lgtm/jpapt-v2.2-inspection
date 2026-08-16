# JSON reference

この文書では主要JSON/JSONLの標準形を示す。値は説明用であり、hash/revision/candidate IDを手でコピーして使うためのテンプレートではない。生成可能なidentityは実script/CLIが生成する。

## `bucket-manifest.json`

Bucket initializerが生成するidentity record。

```json
{
  "schema_version": 1,
  "bucket_id": "gawohok7/jpapt-v2.2-dev-bucket",
  "model": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision_requested": "main",
    "revision_resolved": "0123456789abcdef0123456789abcdef01234567",
    "task": "automatic-speech-recognition",
    "library": "nemo",
    "language": "ja",
    "license": "cc-by-4.0",
    "architecture": "parakeet"
  },
  "profile_set": "parakeet-tdt-ctc-v1"
}
```

実fieldはRust CLI実装を正本とし、unknown fieldを任意に増やさない。

## Candidate `metadata.json`

human-authored metadataは最小にする。

```json
{
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "artifacts": {
        "primary": "ctc/model.onnx"
      },
      "tokenizer": "tokenizer/vocabulary.json"
    },
    "tdt": {
      "artifacts": {
        "encoder": "tdt/encoder.onnx",
        "predictor": "tdt/predictor.onnx",
        "joint": "tdt/joint.onnx"
      },
      "tokenizer": "tokenizer/vocabulary.json"
    }
  }
}
```

candidate ID、SHA256、size、blank ID、tensor bindingはここへ手書きしない。

## `nemo-reference-quality.json`

Python `parakeet-nemo-reference`が生成する。CER/WERは含めない。

```json
{
  "schema_version": 1,
  "reference_run_id": "nemo-0123456789ab-ctc-a1b2c3d4e5f6",
  "source": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision_resolved": "0123456789abcdef0123456789abcdef01234567",
    "model_file": "parakeet-tdt_ctc-0.6b-ja.nemo",
    "model_file_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "library": "nemo",
    "language": "ja",
    "license": "cc-by-4.0"
  },
  "decoder": "ctc",
  "normalization": "asr_metrics_v1",
  "samples": [
    {
      "id": "jsut-0001",
      "audio_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "reference_text": "正解テキスト",
      "text": "NeMoの文字起こし",
      "normalized_text": "NeMoの文字起こし"
    }
  ]
}
```

`normalized_text`はPythonで生成されるが、Rustが再計算する。

## `nemo-onnx-validation.json`

構造の概略:

```json
{
  "schema_version": 1,
  "profile_id": "parakeet-nemo-onnx-v1",
  "source": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision_requested": "main",
    "revision_resolved": "0123456789abcdef0123456789abcdef01234567",
    "library": "nemo",
    "language": "ja",
    "license": "cc-by-4.0",
    "datasets": ["reazon-research/reazonspeech"],
    "model_file": "parakeet-tdt_ctc-0.6b-ja.nemo",
    "model_file_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "environment": {
    "python": "3.12.x",
    "nemo": "...",
    "torch": "...",
    "onnx": "...",
    "onnxruntime": "1.28.0",
    "opset": 18,
    "exporter": "nemo_export",
    "dynamo": false
  },
  "resolved_model": {
    "architecture": "hybrid_fastconformer_tdt_ctc",
    "supported_decoders": ["ctc", "tdt"],
    "default_decoder": "tdt",
    "sample_rate_hz": 16000,
    "n_mels": 0,
    "normalize": "<checkpoint-derived>",
    "dither": 0.0,
    "xscaling": false,
    "tokenizer_type": "sentencepiece",
    "vocab_size": 3072,
    "ctc_blank_id": 3072,
    "tdt_durations": [0, 1, 2, 3, 4]
  },
  "frontend": {
    "location": "outside_onnx",
    "fixture_dither": 0.0,
    "feature_shape_verified": true,
    "parity": {
      "max_abs": 0.0,
      "mean_abs": 0.0,
      "relative_l2": 0.0
    }
  },
  "artifacts": [],
  "gates": {},
  "obstacles": []
}
```

上記`n_mels: 0`等は記入可能値の例ではない。実validatorは`n_mels > 0`を要求する。checkpointから取得した実値を記録することを示すための構造例である。完全なrequired fieldsはJSON SchemaとRust typed contractを参照する。

## `quality-samples.jsonl`

1行1sample。

```json
{"schema_version":1,"sample_id":"jsut-0001","audio_sha256":"...","reference_text":"正解","nemo":{"text":"...","normalized_text":"...","cer":0.01,"wer":0.02},"onnx":{"text":"...","normalized_text":"...","cer":0.01,"wer":0.02},"delta":{"cer":0.0,"wer":0.0},"normalized_text_match":true}
```

## `quality-comparison.json`

```json
{
  "schema_version": 1,
  "comparison": {
    "reference_run_id": "nemo-...",
    "candidate_run_id": "run-...",
    "decoder": "ctc",
    "normalization": "asr_metrics_v1",
    "sample_count": 100
  },
  "source": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision_resolved": "...",
    "model_file": "parakeet-tdt_ctc-0.6b-ja.nemo",
    "model_file_sha256": "..."
  },
  "quality": {
    "nemo": {"cer": 0.05, "wer": 0.10},
    "onnx": {"cer": 0.051, "wer": 0.102},
    "regression": {"cer": 0.001, "wer": 0.002},
    "normalized_text_match_rate": 0.97
  },
  "thresholds": {
    "max_cer_regression": 0.01,
    "max_wer_regression": 0.02
  },
  "acceptance": {
    "passed": true,
    "cer_passed": true,
    "wer_passed": true,
    "failed_checks": []
  }
}
```

threshold値は例示であり標準defaultではない。

## `run-context.json`

run-contextはmodel/config/candidate/provider/evaluation/dataset/runtime identityを結ぶ。major identityに`null`を入れて後で補完する運用を避ける。

最低限の考え方:

```text
run_id
model_id
environment_id
provider_id
evaluation_id
artifact identity
git identity
runtime identity
revision snapshot
resolved config
metadata.candidate generated contract
```

## `metrics.json`

通常`asr-eval evaluate`のaggregate result。quality comparisonとは別artifactである。通常performance/provider情報とNeMo conversion regressionを1つの曖昧なscoreへ合成しない。
