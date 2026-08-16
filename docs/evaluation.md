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

NeMoでもTransformersでもこの考え方は同じです。比較する中間tensorだけがarchitectureによって変わります。

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

manifestと`datasets-lock.json`からdeterministicにsampleを選びます。

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

評価前のaudio contractは全target共通です。

```text
float32
mono
16 kHz
finite
C-contiguous
```

ここから先のfrontendはmodel/framework固有です。

## Architecture固有のparity checkpoint

共通ルールは「そのarchitectureで意味のある境界を比較する」です。

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

現状のONNX evaluatorはCTC中心です。TDT/Whisperの上記checkpointは共通設計上の目標であり、全てが実装済みという意味ではありません。

## ReferenceとDataset正解は別物

次を混同しないでください。

```text
dataset ground truth
  = ASR品質の正解

canonical reference output
  = conversion parityの正解
```

canonical reference自身がdatasetに対して誤認識する可能性はあります。その場合でも、正しいONNX変換はreferenceと同じ挙動を再現することを目指します。

## Config version

評価時には必ず1つのconfig versionを固定します。

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

Runは1つの具体的な実行です。

```text
Linux CPU run
Windows CPU run
macOS CPU run
macOS CoreML run
```

cross-platform評価ではこれらが同じexperiment IDを共有します。

## 出力

```text
results/<run>/
  run-context.json
  samples.jsonl
  metrics.json
```

### `run-context.json`

再現性情報を保存します。

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

主要指標:

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

runにはrequested providerだけでなく、provider availabilityやfallback情報も残す必要があります。

```text
CPU
CUDA
DirectML
CoreML
```

session生成成功だけでは全nodeが希望EPで実行された証明にはなりません。

## Acceptance

release品質のthresholdはBucket側のversioned `evaluation-schema.json`で管理します。GitにあるJSON Schemaは構造検証用であり、品質thresholdそのものではありません。

## Promotion

原則としてaccepted full runをpromotion gateにします。

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

両実装は次を共有します。

```text
manifest identity
materialized sample
config version
revision bundle
candidate identity
run-context schema
result schema
benchmark schema
```

framework差分はこれらの外側ではなく、frontend/runtime/decoder adapterへ閉じ込めます。