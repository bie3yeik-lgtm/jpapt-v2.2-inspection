# 評価仕様

## 目的

本リポジトリの評価は、frameworkに依存しない共通評価と、architecture固有のparity確認を分けて扱います。

大きく2種類あります。

### ASR品質評価

Datasetの正解文字列とcandidate出力を比較します。

```text
CER
WER
```

### Conversion / Runtime parity

canonical referenceとcandidateを比較します。

```text
reference output
  ↕
candidate output
```

NeMoでもTransformersでも考え方は同じで、比較する中間tensorやdecoder stateだけがarchitectureによって変わります。

## Suite

| Suite | Sample数 | 主目的 |
|---|---:|---|
| `smoke` | 12 | pipeline健全性、軽量回帰 |
| `parity` | 48 | reference/candidate parity |
| `coreml-parity` | 40 | CoreML EP互換性・shape境界 |
| `full` | 768 | 品質・性能・release gate |

設定:

```text
config/evaluation/*.toml
```

manifest:

```text
evaluation/manifests/*.jsonl
```

## Dataset selection

```text
manifest
  +
datasets-lock
  ↓
stable-hash selection
  ↓
materialization
```

同じdataset revision、seed、selection条件なら同じsample集合になります。

## CanonicalAudio

全target共通:

```text
float32
mono
16 kHz
finite
C-contiguous
```

ここから先のfrontendはmodel/framework固有です。

## Architecture固有のparity checkpoint

### Parakeet CTC

```text
frontend
encoder
CTC logits
token IDs
text
```

### Parakeet TDT

```text
frontend
encoder
predictor/joint
duration/token sequence
text
```

### Whisper

```text
input features
encoder output
decoder sequence / logits
generated token IDs
text
```

上記はarchitectureとして望ましいcheckpointです。現在どこまで実行可能かはevaluator capabilityで判断します。

## Evaluator capability

Targetが要求するdecoderと、実際のevaluatorが対応するdecoderを分離します。

```text
Target decoder
  +
config/evaluators/<evaluator>.toml
  ↓
validate-evaluator-capability.py
```

現在:

```text
python-onnx -> ctc
rust-onnx   -> ctc
```

です。

したがってTDT/Whisper targetが停止する場合、それはBucketやrevision contractが非対応だからではなく、選択evaluatorのcapabilityが未実装だからです。

workflowへdecoder固有条件を増やさず、runtime実装とcapability declarationを拡張します。

## ReferenceとDataset正解は別物

```text
dataset ground truth
  = ASR品質の正解

canonical reference output
  = conversion parityの正解
```

canonical reference自身がdatasetに対して誤認識していても、ONNX conversion parityではreference挙動を再現することが目的です。

## Config version

評価時には1つのconfig versionを固定します。

```text
config-NNNNNN
  ├── reference.json
  ├── evaluation-schema.json
  └── datasets-lock.json
```

runには`revisions.config_version`とbundle hashを保存します。

## Experiment / Run

Experimentは論理的な評価単位です。

```text
cross-platform-parity-000023
```

Experiment IDは各workflowが独自採番せず、中央Allocatorから取得します。

```text
workflow
  ↓
HF Central Sequence Allocator
  ↓
experiment ID
```

Runは1つの具体的な実行です。

```text
Linux CPU run
Windows CPU run
macOS CPU run
macOS CoreML run
```

cross-platform評価ではこれらが同じexperiment IDを共有します。

中央Allocatorが採番するため、複数Repositoryから同じBucketに対して評価を開始してもexperiment suffixは衝突しません。

## 出力

```text
results/<run>/
  run-context.json
  samples.jsonl
  metrics.json
```

### `run-context.json`

```text
candidate / artifact SHA
experiment ID
config version
revision identities
HF routing snapshot
Git revision
host
runtime/provider
evaluation suite
```

### `samples.jsonl`

sample単位の結果です。

### `metrics.json`

aggregate metricとacceptance結果です。

## Performance metric

```text
RTF = processing_time / audio_duration
```

可能な限り次を分離します。

```text
audio decode
resample
frontend
ORT inference
decoder
postprocess
total
```

Python→Rust化で改善しやすい部分とORT kernel自体の性能を混同しないためです。

## Execution Provider

runにはrequested providerだけでなくprovider availabilityやfallback情報も残します。

```text
CPU
CUDA
DirectML
CoreML
```

session生成成功だけでは全nodeが希望EPで実行された証明にはなりません。

## Acceptance

release品質thresholdはBucket側のversioned `evaluation-schema.json`で管理します。GitにあるJSON Schemaは構造検証用です。

## Promotion

```text
candidate
  ↓
full evaluation
  ↓
acceptance.passed
  ↓
artifact SHA一致確認
  ↓
Model Repoへpromotion
```

## Python / Rust共通contract

```text
manifest identity
materialized sample
config version
revision bundle
candidate identity
experiment identity
run-context schema
result schema
benchmark schema
```

framework差分はfrontend/runtime/decoder adapterへ閉じ込め、採番やstorage lifecycleへ持ち込みません。

関連文書:

```text
docs/multi-framework-asr.md
docs/central-allocator.md
docs/github-actions.md
```
