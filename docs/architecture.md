# アーキテクチャ

## 目的

本リポジトリは、日本語ASRモデルを共通の運用基盤で扱い、原モデル固定、canonical reference生成、ONNX化、candidate評価、複数Execution Providerでの検証、Hugging Face Model Repoへのpromotionまでを再現可能にするための開発基盤です。

対象frameworkは1つに固定しません。

```text
NeMo系          例: NVIDIA Parakeet
Transformers系  例: Kotoba Whisper
```

framework差分をBucket構造や評価履歴へ持ち込まず、target設定・reference adapter・export adapter・decoder/runtime・evaluator capabilityへ閉じ込めます。

## 共通ライフサイクル

```text
Target
  ↓
Versioned Config
  ↓
Canonical Reference
  ↓
Export / Build
  ↓
Candidate
  ↓
Experiment
  ↓
Run
  ↓
Benchmark / Acceptance
  ↓
Promotion
```

NeMo/Transformers、CTC/TDT/Whisper autoregressiveの違いは、この流れ自体を変更しません。

## 責務の分離

### GitHub Repository

```text
source code
config/
evaluation/schemas/
evaluation/manifests/
GitHub Actions
運用スクリプト
docs/
```

### Hugging Face Bucket

```text
README.md
config/
experiments/
candidates/
reference/
runs/
benchmarks/
scripts/
tmp/
```

mutableな開発・評価履歴を保存します。

### Hugging Face Model Repo

検証済みdevelopment/release artifactを保存します。Bucketは作業履歴、Model Repoはpromotion先です。

## TargetとRouting

Targetは安定したmodel semanticsを表します。

```text
model
canonical framework
upstream
tokenizer / processor
decoder contract
```

静的設定:

```text
config/models/<model-id>.toml
config/hf-targets/<target-id>.toml
```

現在のstorage routing:

```text
vars.HF_TARGETS_JSON
```

`HF_BUCKET`はTarget identityそのものではなく、運用上変更可能です。

## Config version

```text
config/current.json
config/versions/config-NNNNNN/
  README.md
  reference.json
  evaluation-schema.json
  datasets-lock.json
```

3 JSONがcanonical revision bundleです。`README.md`は中央Allocatorによる番号予約・provenanceです。

通常実行は`current.json`、過去再現は`HF_CONFIG_VERSION=config-NNNNNN`を使います。

## 中央Allocator

Candidate、Experiment、Config Versionの数値suffixは人間が決めません。

```text
複数Repository
      ↓
HF Central Sequence Allocator
      ↓
対象Bucketの既存最大suffix + 1
```

中央Allocator RepositoryでBucket単位に直列化するため、複数Repositoryから同じBucketへ同時要求しても同じ番号を発行しません。

採番後はID直下のREADMEを予約し、さらにBucketルートREADMEの現在番号blockを更新します。

## `reference.json`のidentity

```text
development_artifact  自分たちが生成・公開するModel Repo snapshot
upstream              変換元となる原モデルsnapshot
tokenizer             tokenizer / processor snapshot
reference             canonical expected resultを生成する実装
canonical_framework   nemo / transformers / ...
decoders              supported/default decoder
```

`HF_BUCKET`はprovenanceではなくroutingなので記録しません。

## 共通ASR境界

```text
audio asset
  ↓
decode / resample
  ↓
CanonicalAudio
  - float32
  - mono
  - 16 kHz
  ↓
model-specific frontend
```

### Parakeet例

```text
CanonicalAudio
  ↓
FastConformer frontend/encoder
  ↓
CTC head または TDT path
  ↓
decoder
```

### Whisper例

```text
CanonicalAudio
  ↓
Whisper feature extraction / encoder
  ↓
autoregressive decoder
  ↓
tokenizer / processor
```

## ReferenceとCandidate

Reference:

```text
CanonicalAudio
  ↓
canonical framework adapter
  ↓
expected output
```

Candidate:

```text
CanonicalAudio
  ↓
candidate runtime contract
  ↓
ONNX Runtime
  ↓
candidate output
```

Parityではarchitectureに応じた中間点も比較します。

## Evaluator capability

Targetが要求するdecoderと、evaluator実装が現在扱えるdecoderを分離します。

```text
Target decoder contract
        +
config/evaluators/<evaluator>.toml
        ↓
validate-evaluator-capability.py
```

workflow自身は`ctc`等を条件分岐しません。

現在:

```text
python-onnx -> ctc
rust-onnx   -> ctc
```

TDT/Whisper runtime追加時はcapabilityとruntime adapterを拡張します。

## PythonとRust

Python:

```text
framework integration
reference
export
dataset materialization
Python ONNX evaluation
```

Rust:

```text
production-oriented ONNX runtime
audio
metrics
evaluation
binary release
```

現在のPython/Rust evaluator capabilityはCTC中心です。これは共通storage/revision設計の制約ではありません。

## Execution Provider

```text
model/target
  ×
evaluator
  ×
provider
  ×
environment
  ×
evaluation suite
```

CPU/CUDA/DirectML/CoreMLはmodel identityではなく実行backendです。

## 再現性

各runは最低限次を記録します。

```text
HF target id
実行時HF Bucket / Model Repo
config version
revision bundle hash
candidate id / artifact SHA-256
experiment id
upstream / tokenizer / development artifact revision
reference revision
Git commit
OS / architecture
runtime / provider
evaluation suite
```

現在の`HF_TARGETS_JSON`が変わっても、過去runはrun-contextのrouting snapshotから再現します。

## 関連文書

```text
docs/multi-framework-asr.md    framework/decoder差分
docs/central-allocator.md      中央採番
docs/hf-layout.md              Bucket構造
docs/hf-bucket-operations.md   Bucket運用仕様
docs/evaluation.md             評価仕様
docs/onnx-export.md            export/candidate生成
docs/github-actions.md         Actions運用
```
