# マルチFramework ASR設計

## この文書の目的

本リポジトリではNeMoとTransformersを同じASR開発基盤へ載せます。この文書では**共通部分とframework/runtime差分だけ**を整理します。Bucket、run、candidate、config versionなどの運用構造はframeworkによって変えません。

## 共通Target model

Targetは安定したmodel semanticsを表す論理単位です。

```text
model semantics
canonical framework
upstream model
tokenizer / processor
decoder contract
```

静的設定:

```text
config/models/<model-id>.toml
config/hf-targets/<target-id>.toml
```

一方、現在どのBucket/Model Repoへ接続するかは運用routingです。

```text
vars.HF_TARGETS_JSON
```

`HF_BUCKET`はTarget identityそのものではなく、将来変更可能です。

## 現在の代表target

| Target | Framework | Upstream | Default decoder |
|---|---|---|---|
| `parakeet-tdt_ctc-0.6b-ja` | NeMo | `nvidia/parakeet-tdt_ctc-0.6b-ja` | `ctc` |
| `kotoba-whisper-v1.0` | Transformers | `kotoba-tech/kotoba-whisper-v1.0` | `whisper_autoregressive` |

## 共通するもの

次はNeMo/Transformersで同じです。

```text
HF Bucket lifecycle
中央Allocator
config/current.json + config/versions/
reference.json identity model
datasets-lock
evaluation manifests
CanonicalAudio
candidate / experiment / run IDs
run-context schema
Execution Provider model
benchmark layout
promotion lifecycle
```

## 違うもの

| 領域 | NeMo / Parakeet | Transformers / Whisper |
|---|---|---|
| canonical loader | NeMo | Transformers |
| processor | NeMo model/frontend | `AutoProcessor`等 |
| decoder | CTC / TDT | autoregressive Whisper decoder |
| export graph | 1 graph中心の場合あり | encoder/decoder/decoder-with-past等の複数graphになり得る |
| reference adapter | NeMo adapter | Transformers adapter |
| 現在のONNX evaluator | CTC capabilityあり | autoregressive capability未実装 |

## CanonicalAudioまでを共通化する理由

```text
audio asset
  ↓
float32 / mono / 16kHz
  ↓
CanonicalAudio
```

ここまではframework共通です。model固有feature extractionをこの前に混ぜると、dataset/audio問題とmodel問題を分離できなくなるためです。

## NeMo / Parakeet

```text
CanonicalAudio
  ↓
NeMo frontend
  ↓
FastConformer encoder
  ↓
CTC head または TDT path
  ↓
decoder
```

### CTC

現在のPython/Rust ONNX evaluatorが対応する主要decoderです。

```text
logits
  ↓
argmax / collapse / blank removal
  ↓
text
```

### TDT

predictor/joint/duration-aware decodingが必要です。Target/revision/storage contract上は表現できますが、現在のevaluator capabilityにはまだ追加されていません。

## Transformers / Whisper

```text
CanonicalAudio
  ↓
processor / feature extraction
  ↓
encoder
  ↓
autoregressive decoder
  ↓
generated token IDs
  ↓
processor/tokenizer decode
```

Reference adapterではmodel repoとtokenizer/processor repoを独立して固定できます。

Whisper ONNX candidateは複数graphを持てます。

```text
encoder.onnx
decoder.onnx
decoder_with_past.onnx
```

ファイル名そのものをcontractにせず、candidate metadataでartifact roleを記述します。

## `reference.json`

全frameworkで同じshapeを使います。

```json
{
  "schema_version": 1,
  "development_artifact": {
    "repo_id": "owner/dev-model-repo",
    "revision": "<sha>"
  },
  "upstream": {
    "repo_id": "vendor/upstream-model",
    "revision": "<sha>"
  },
  "tokenizer": {
    "repo_id": "vendor/tokenizer-or-processor",
    "revision": "<sha>"
  },
  "reference": {
    "id": "framework-reference-v1",
    "revision": "<implementation-revision>",
    "canonical_framework": "transformers"
  },
  "decoders": {
    "supported": ["whisper_autoregressive"],
    "default": "whisper_autoregressive"
  }
}
```

NeMoだから別schema、Transformersだから別schema、とはしません。

## Evaluator capability

Targetが「どのdecoderを必要とするか」と、evaluatorが「どのdecoderを現在実装しているか」は別contractです。

Target側:

```text
reference.json.decoders
config/hf-targets/<target>.toml
```

Evaluator側:

```text
config/evaluators/python-onnx.toml
config/evaluators/rust-onnx.toml
```

実行前に:

```text
scripts/ci/validate-evaluator-capability.py
```

が両者を照合します。

現在:

```text
python-onnx supported_decoders = ["ctc"]
rust-onnx   supported_decoders = ["ctc"]
```

です。

この分離により、TDTやWhisper autoregressiveを追加するときにGitHub Actionsへdecoder固有`if`を増やす必要がありません。runtime実装後にevaluator capabilityを拡張します。

## Storage routing

`HF_TARGETS_JSON`は現在時点のrouting snapshotです。

```json
{
  "target-a": {
    "HF_BUCKET": "owner/bucket-a",
    "HF_MODEL_REPO": "owner/model-a"
  },
  "target-b": {
    "HF_BUCKET": "owner/bucket-b",
    "HF_MODEL_REPO": "owner/model-b"
  }
}
```

同一snapshot内では`HF_BUCKET`は一意です。ただし将来targetが別Bucketへ移動することは許容します。過去runはrun-contextのrouting snapshotから再現します。

## 採番はframework非依存

```text
candidate
experiment
config version
```

の番号はNeMo/Transformersで別counterを持ちません。物理Bucket内のcollectionを中央Allocatorが走査し、最大suffix+1を発行します。

複数Repositoryで同じBucketを使う場合も同じ中央Allocatorへ要求します。

## 評価workflowの現状

`Validate HF Layout`はどちらのframeworkでも使用できます。

評価workflowはtarget解決とrevision検証までは共通です。その後、選択targetのdecoderをevaluator capabilityと照合します。

Whisper targetが現在停止する理由は、workflowにWhisper禁止条件があるためではなく、`python-onnx` / `rust-onnx` capabilityに`whisper_autoregressive`がまだ存在しないためです。

```text
Target/config/reference/storage contract    対応済み
Transformers reference adapter              対応済み
Whisper autoregressive evaluator capability 未実装
```

## 新しいframework/decoderを追加する場合

最低限必要なもの:

```text
1. config/models/<id>.toml
2. config/hf-targets/<id>.toml
3. canonical reference adapter
4. export adapter
5. candidate runtime contract
6. decoder/runtime implementation
7. config/evaluators/<evaluator>.toml のcapability拡張
8. target固有parity checkpoint
```

Bucket tree、中央採番、run schemaをframeworkごとに増やす必要はありません。
