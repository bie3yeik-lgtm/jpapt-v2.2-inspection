# マルチFramework ASR設計

## この文書の目的

本リポジトリではNeMoとTransformersを同じASR開発基盤へ載せます。この文書では**共通部分と差分だけ**を整理します。Bucket、run、candidate、config versionなどの運用構造はframeworkによって変えません。

## 共通Target model

Targetは次を組み合わせた論理単位です。

```text
model semantics
canonical framework
upstream model
tokenizer / processor
decoder contract
HF storage routing
```

静的設定:

```text
config/models/<model-id>.toml
config/hf-targets/<target-id>.toml
```

実行時storage routing:

```text
vars.HF_TARGETS_JSON
```

## 現在の代表target

| Target | Framework | Upstream | Default decoder |
|---|---|---|---|
| `parakeet-tdt_ctc-0.6b-ja` | NeMo | `nvidia/parakeet-tdt_ctc-0.6b-ja` | `ctc` |
| `kotoba-whisper-v1.0` | Transformers | `kotoba-tech/kotoba-whisper-v1.0` | `whisper_autoregressive` |

## 共通するもの

次はNeMo/Transformersで同じです。

```text
HF Bucket lifecycle
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

差分は主に以下です。

| 領域 | NeMo / Parakeet | Transformers / Whisper |
|---|---|---|
| canonical loader | NeMo | Transformers |
| processor | NeMo model/frontend | `AutoProcessor`等 |
| decoder | CTC / TDT | autoregressive Whisper decoder |
| export graph | 1 graph中心の場合あり | encoder/decoder/decoder-with-past等の複数graphになり得る |
| reference adapter | NeMo adapter | Transformers adapter |
| 現在のRust runtime | CTC対応 | 未対応 |

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

代表的な処理:

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

現在のPython/Rust ONNX evaluatorの主要実装対象です。

```text
logits
  ↓
argmax / collapse / blank removal
  ↓
text
```

### TDT

predictor/joint/duration-aware decodingが必要です。Target contract上は表現できますが、Rust production pathはまだCTCと同等には実装されていません。

## Transformers / Whisper

代表的な処理:

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

Reference adapterではmodel repoとtokenizer/processor repoを独立して固定できる設計です。

Whisper ONNX candidateは複数graphを持てます。

```text
encoder.onnx
decoder.onnx
decoder_with_past.onnx
```

ファイル名そのものをcontractにせず、candidate metadataでartifact roleを記述するのが基本方針です。

## `reference.json`

全frameworkで同じ形を使います。

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

## Storage routing

`HF_TARGETS_JSON`は現在時点のroutingです。

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

## 評価workflowの現状

`Validate HF Layout`はどちらのframeworkでも使用できます。

評価workflowはtarget解決とrevision検証までは共通ですが、現状のPython/Rust evaluatorはCTC中心です。そのためWhisper targetは、decoder compatibility checkで明示的に停止します。

これは「Transformersをサポートしていない」という意味ではありません。

```text
Target/config/reference/storage contract  対応済み
Transformers reference adapter             対応済み
Whisper ONNX autoregressive evaluator       未完成
```

という実装段階の違いです。

## 新しいframeworkを追加する場合

最低限必要なもの:

```text
1. config/models/<id>.toml
2. config/hf-targets/<id>.toml
3. canonical reference adapter
4. export adapter
5. candidate runtime contract
6. decoder implementation
7. target固有parity checkpoint
```

Bucket treeやrun schemaをframeworkごとに増やす必要はありません。