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

## Frameworkとの関係

Rust runtimeはNeMoやTransformersそのものを実行しません。評価対象はexport済みdeployment artifactです。

```text
NeMo/Transformers
  ↓ export
ONNX Candidate
  ↓
Rust runtime
```

したがってRust側の実装差分はframework名よりcandidate runtime contractとdecoderです。

## Evaluator capability

Rust evaluatorが現在扱えるdecoderはworkflow内の条件式ではなく:

```text
config/evaluators/rust-onnx.toml
```

で宣言します。

実行前に:

```bash
python scripts/ci/validate-evaluator-capability.py \
  --evaluator rust-onnx \
  --decoder <resolved-decoder>
```

を行います。

現在のcapability:

```text
supported_decoders = ["ctc"]
```

TDTやWhisper runtimeを追加するときは、Rust実装とcapability定義を拡張します。`rust-eval.yml`へdecoder固有のshell条件を追加しません。

## 現在の対応範囲

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

Target/config/BucketがWhisperに対応していることと、Rust evaluator capabilityがWhisperを実装していることは別です。

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

run-contextには実行時routing snapshotも保存します。

```text
hf_target_id
hf_bucket
hf_model_repo
experiment_id
candidate_id
```

これにより将来`HF_TARGETS_JSON`が変更されても過去runを追跡できます。

## Experiment ID

`rust-eval.yml`のexperiment IDはworkflow自身で採番しません。

```text
rust-eval workflow
  ↓
HF Central Sequence Allocator
  ↓
rust-eval-NNNNNN
```

同じcross-platform workflow内のmatrix jobは1つのexperiment IDを共有し、それぞれ独立run IDを生成します。

複数Repositoryから同一Bucketを利用しても中央Allocatorで排他されます。

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

`rust-ci.yml`:

```text
Linux CPU
Windows DirectML feature build/test
macOS CoreML feature build/test
rustfmt advisory
```

`rust-eval.yml`:

```text
existing candidate selection
  ↓
central experiment allocation
  ↓
target/revision resolution
  ↓
rust-onnx capability validation
  ↓
cross-platform evaluation
```

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

関連文書:

```text
docs/multi-framework-asr.md
docs/central-allocator.md
docs/github-actions.md
```
