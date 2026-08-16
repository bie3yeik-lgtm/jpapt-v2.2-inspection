# Rust Runtime / Evaluator

## 目的

Rustはproduction寄りのONNX Runtime実行、audio処理、decoder、metric計算、評価artifact生成を担当します。Python側のframework ecosystemをそのままRustへ再実装することは目的ではありません。

## 境界

```text
Python側
  target/config解決
  dataset解決・materialization
  canonical reference/export
        ↓
resolved manifest
candidate artifact
revision bundle
        ↓
Rust側
  audio
  ONNX Runtime
  decoder
  metrics
  run-context
```

HF `datasets`/Arrowの意味論をRustへ複製せず、Pythonが解決済みの入力を渡します。

## Crate構成

```text
rust/crates/
├── asr-runtime/
├── asr-audio/
├── asr-metrics/
└── asr-eval/
```

### `asr-runtime`

ONNX Runtime sessionとExecution Providerを扱います。

### `asr-audio`

runtime側のaudio処理を担当します。

### `asr-metrics`

CER/WER等のmetricを担当します。

### `asr-eval`

manifestを読み、runtime、decoder、metrics、run-context出力を統合します。

## Frameworkとの関係

Rust runtimeはNeMoそのものやTransformersそのものを実行しません。評価対象はexport済みdeployment artifactです。

```text
NeMo/Transformers
  ↓ export
ONNX Candidate
  ↓
Rust runtime
```

そのためRust側の主要差分はframework名ではなくcandidate runtime contractとdecoderです。

## 現在の対応範囲

現状の主要実装はCTCです。

```text
ONNX inference
  ↓
CTC logits
  ↓
CTC decode
  ↓
text / metrics
```

未完成の代表例:

```text
TDT predictor/joint decoding
Whisper autoregressive decoding
Whisper KV-cache runtime
```

Target/config/BucketがWhisperに対応していることと、Rust runtimeがWhisper inferenceに対応していることは別です。

## Config versionとRun Context

Rust evaluatorもPythonと同じrevision bundleを読みます。

```text
config_version
development_artifact
upstream
tokenizer
reference
decoders
```

run-contextにはさらに実行時routing snapshotを保存します。

```text
hf_target_id
hf_bucket
hf_model_repo
experiment_id
candidate_id
```

これにより将来`HF_TARGETS_JSON`が変更されても過去runを追跡できます。

## Build

CPU:

```bash
cargo build --release -p asr-eval \
  --no-default-features \
  --features cpu
```

Windows DirectML:

```bash
cargo build --release -p asr-eval \
  --no-default-features \
  --features cpu,directml
```

macOS CoreML:

```bash
cargo build --release -p asr-eval \
  --no-default-features \
  --features cpu,coreml
```

CUDA-capable環境:

```bash
cargo build --release -p asr-eval \
  --no-default-features \
  --features cpu,cuda
```

## GitHub Actions

`.github/workflows/rust-ci.yml`では主に次を検証します。

```text
Linux CPU
Windows DirectML feature build/test
macOS CoreML feature build/test
rustfmt advisory
```

`rust-eval.yml`は既存candidateを選択してcross-platform評価を行い、workflow全体に`rust-eval-NNNNNN`のexperiment IDを自動発行します。

## Release

`rust-release.yml`は`v*` tagまたは手動tag入力からbinary archiveと`SHA256SUMS`を生成し、GitHub Releaseへ公開します。

HF Model Repoのmodel artifact promotionとは別のrelease lifecycleです。

## Pythonとの比較

Python/Rust比較では次を揃えます。

```text
same candidate
same artifact SHA-256
same config version
same samples
same provider
same decoder
same machine where possible
```

比較値:

```text
ORT-only RTF
end-to-end RTF
non-ORT overhead
peak RAM
CER/WER
```

Rust化によってI/Oやdecoder overheadが改善しても、同じORT kernelの純粋なinference時間が大きく変化するとは限りません。