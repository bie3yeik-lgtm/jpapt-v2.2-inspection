# JSON reference

この文書では主要JSON/JSONLの標準形を示す。hash、revision、candidate ID、checkpoint依存値を手作業で埋めるためのテンプレートではない。生成可能なidentityは実script/CLIが生成する。

## `bucket-manifest.json`

Bucket initializerが生成するidentity record。以下は実E2Eで用いたKotoba系の形に合わせた例である。

```json
{
  "schema_version": 1,
  "bucket_id": "gawohok7/ci-test",
  "model": {
    "repo_id": "kotoba-tech/kotoba-whisper-v2.0",
    "revision_requested": "main",
    "revision_resolved": "0123456789abcdef0123456789abcdef01234567",
    "task": "automatic-speech-recognition",
    "library": "transformers",
    "language": "ja",
    "license": "apache-2.0",
    "architecture": "whisper"
  },
  "profile_set": "<source-controlled-profile-set>"
}
```

`revision_resolved`と`profile_set`は生成結果を使う。例示文字列を実入力へ流用しない。

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
      "id": "sample-0001",
      "audio_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "reference_text": "正解テキスト",
      "text": "NeMoの文字起こし",
      "normalized_text": "NeMoの文字起こし"
    }
  ]
}
```

`reference_run_id`は実装上、model revision prefixに加えてsample-set digest prefixも含む。`normalized_text`はPythonで生成されるがRustが再計算する。

## `nemo-onnx-validation.json`

このJSONは手書きしない。NeMo export/reference jobがcheckpointと実artifactから生成する。

Model Cardから固定できる領域:

```json
{
  "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
  "library": "nemo",
  "language": "ja",
  "license": "cc-by-4.0",
  "datasets": ["reazon-research/reazonspeech"],
  "model_file": "parakeet-tdt_ctc-0.6b-ja.nemo"
}
```

checkpointから生成しなければならない領域:

```text
revision_resolved
model_file_sha256
n_mels
normalize
dither
xscaling
ctc_blank_id
tdt_durations
predictor state shapes
tensor names/shapes
artifact SHA256/size
external-data SHA256/size
frontend parity values
gate evidence
obstacle evidence
```

これらについて標準的な数値をdocsへ置かない。別世代Parakeetの値や一般的Whisper値を流用せず、exact `.nemo`から得た値だけをJSONへ記録する。

構造上の主要top-level fieldは次のとおり。

```text
schema_version = 1
profile_id = parakeet-nemo-onnx-v1
source
environment
resolved_model
frontend
artifacts
gates
obstacles
```

完全なrequired fieldsと型は`evaluation/schemas/nemo-onnx-validation.schema.json`およびRust `asr-eval::nemo_onnx` typed contractを正本とする。

## `quality-samples.jsonl`

1行1sample。Rustが生成する。

```json
{"schema_version":1,"sample_id":"sample-0001","audio_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","reference_text":"正解","nemo":{"text":"NeMo出力","normalized_text":"NeMo出力","cer":0.01,"wer":0.02},"onnx":{"text":"ONNX出力","normalized_text":"ONNX出力","cer":0.01,"wer":0.02},"delta":{"cer":0.0,"wer":0.0},"normalized_text_match":false}
```

CER/WERは説明用の数値でありdefault thresholdではない。

## `quality-comparison.json`

```json
{
  "schema_version": 1,
  "comparison": {
    "reference_run_id": "nemo-0123456789ab-ctc-a1b2c3d4e5f6",
    "candidate_run_id": "run-example",
    "decoder": "ctc",
    "normalization": "asr_metrics_v1",
    "sample_count": 100
  },
  "source": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision_resolved": "0123456789abcdef0123456789abcdef01234567",
    "model_file": "parakeet-tdt_ctc-0.6b-ja.nemo",
    "model_file_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
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

threshold値は説明用でありrepository defaultではない。CLI呼出側が明示する。

## `run-context.json`

run-contextはmodel/config/candidate/provider/evaluation/dataset/runtime identityを結ぶ。major identityに`null`を入れて後で補完する運用を避ける。

最低限の概念:

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

通常`asr-eval evaluate`のaggregate result。NeMo conversion qualityとは別artifactである。performance/provider情報とconversion regressionを1つの曖昧なscoreへ合成しない。
