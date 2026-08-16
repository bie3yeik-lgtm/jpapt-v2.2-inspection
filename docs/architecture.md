# アーキテクチャ

## 目的

本リポジトリは、日本語ASRモデルを共通の運用基盤で扱い、原モデルの固定、canonical reference生成、ONNX化、candidate評価、複数Execution Providerでの検証、Hugging Face Model Repoへのpromotionまでを再現可能にするための開発基盤です。

対象frameworkは1つに固定しません。現在は主に次を扱います。

```text
NeMo系          例: NVIDIA Parakeet
Transformers系  例: Kotoba Whisper
```

frameworkごとの違いをBucket構造や評価履歴の構造へ持ち込まず、差分はtarget設定・reference adapter・export adapter・decoder/runtimeへ閉じ込めます。

## 共通ライフサイクル

すべてのtargetは次の同じ流れで扱います。

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

NeMoかTransformersか、CTCかWhisper autoregressiveかは、この流れ自体を変えるものではありません。

## 責務の分離

### GitHub Repository

Gitで管理するもの:

```text
source code
config/
evaluation/schemas/
evaluation/manifests/
GitHub Actions
運用スクリプト
docs/
```

大容量model、audio、tensor、ONNX実体は原則としてGitへ保存しません。

### Hugging Face Bucket

mutableな開発・評価履歴を保存します。

```text
config/
experiments/
candidates/
reference/
runs/
benchmarks/
scripts/
tmp/
```

### Hugging Face Model Repo

検証済みのdevelopment/release artifactを保存します。Bucketは作業履歴、Model Repoはpromotion先という役割分担です。

## Targetの考え方

Targetは「どのモデルを、どのcanonical framework、decoder、storage routingで扱うか」を表す論理単位です。

静的な意味は次で管理します。

```text
config/models/<model-id>.toml
config/hf-targets/<target-id>.toml
```

実行時のHF storage routingはRepository Variable `HF_TARGETS_JSON` が担当します。`HF_BUCKET`は運用上変更可能であり、model identityそのものではありません。

## Config version

Bucket内のrevision文書は上書きせず、immutableなversionとして管理します。

```text
config/current.json
config/versions/config-NNNNNN/
  reference.json
  evaluation-schema.json
  datasets-lock.json
```

通常実行は`current.json`を参照し、過去runの再現では`HF_CONFIG_VERSION=config-NNNNNN`で明示指定できます。

## `reference.json`のidentity

`reference.json`では以下を独立して固定します。

```text
development_artifact  自分たちが生成・公開するartifactのModel Repo snapshot
upstream              変換元となる原モデルのsnapshot
tokenizer             tokenizer / processorのsnapshot
reference             canonical expected resultを生成する実装
canonical_framework   nemo / transformers / ...
decoders              supported/default decoder
```

`HF_BUCKET`はここには記録しません。Bucketはrouting、`reference.json`はprovenanceです。

## 共通ASR境界

framework差分の前に、audio入力は共通化します。

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

ここから先がtarget固有です。

### Parakeet例

```text
CanonicalAudio
  ↓
FastConformer frontend/encoder
  ↓
CTC head または TDT head
  ↓
decoder
  ↓
text
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
  ↓
text
```

## ReferenceとCandidate

Referenceは「正解系として採用するcanonical implementation」です。

```text
CanonicalAudio
  ↓
canonical framework adapter
  ↓
reference output
```

Candidateは評価対象のdeployment artifactです。

```text
CanonicalAudio
  ↓
candidate runtime contract
  ↓
ONNX Runtime
  ↓
candidate output
```

ONNX parityでは、最終textだけでなく、そのarchitectureで意味のある中間点を比較します。

## PythonとRust

Pythonはframework integrationと開発側の正規処理を担当します。

```text
python/src/parakeet_onnx/
  config/
  hf/
  datasets/
  audio/
  reference/
  export/
  runtime/
  decoding/
  evaluation/
  cli/
```

Rustはproduction寄りのruntime/evaluatorを担当します。

```text
rust/crates/
  asr-runtime/
  asr-audio/
  asr-metrics/
  asr-eval/
```

現状のPython/Rust ONNX evaluatorはCTC中心です。Whisper targetのrevision/layout validationは可能ですが、Whisper autoregressive runtimeはまだ同等に実装されていません。この制約はframework共通仕様ではなく、現在のruntime実装状況です。

## Execution Provider

CPU/CUDA/DirectML/CoreMLはmodel定義ではなく実行backendです。

```text
model/target
  ×
provider
  ×
environment
  ×
evaluation suite
```

として組み合わせます。

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

現在の`HF_TARGETS_JSON`が将来変更されても、過去runはrun-contextに保存されたrouting snapshotから再現します。

## 関連文書

```text
docs/multi-framework-asr.md    framework/decoder差分
docs/hf-layout.md              Bucket構造
docs/hf-bucket-operations.md   Bucket運用仕様
docs/evaluation.md             評価仕様
docs/onnx-export.md            export/candidate生成
docs/github-actions.md         Actions運用
```