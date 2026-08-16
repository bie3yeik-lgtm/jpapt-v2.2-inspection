# Candidate Metadata

## 目的

`metadata.json` は **人間がcandidateの構成を指定する最小入力**です。

人間が決めるのは次だけです。

```text
profile_set
variant -> artifact role/path
必要な場合だけ tokenizer/processor path
```

SHA-256、file size、candidate ID、catalog fingerprint、decoder/profile、tensor I/O、token ID、state/KV metadataは書きません。コードが実artifact・catalog・model/tokenizer configから取得します。

## Canonical form

Parakeet:

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

Whisper:

```json
{
  "profile_set": "whisper-autoregressive-v1",
  "variants": {
    "whisper": {
      "artifacts": {
        "encoder": "encoder.onnx",
        "decoder": "decoder.onnx",
        "decoder_with_past": "decoder_with_past.onnx"
      },
      "tokenizer": "tokenizer"
    }
  }
}
```

Schema:

```text
evaluation/schemas/candidate-metadata.schema.json
```

## 自動解決される値

`CandidateArtifacts.load()` は次を生成・検証します。

```text
candidate_id
    Bucketから取得した場合 .candidate-id
    それ以外はcandidate directory名

catalog id / SHA-256
    config/asr-catalog.json

profile / decoder / artifact contract / features
    profile_set + variant + ASR runtime catalog

artifact SHA-256 / size
    実ファイル

tensor I/O / predictor state / KV-cache names
    ONNX graph inspection

blank/bos/eos/prompt token IDs / generation parameters
    ONNX metadata + vocabulary + generated model/tokenizer config
```

導出できないruntime-critical値は推測しません。candidate validationを失敗させます。

## Tokenizer path

既定配置なら `tokenizer` は省略できます。

Vocabulary profileでは次を探索します。

```text
tokenizer/vocabulary.json
vocabulary.json
tokenizer/vocab.json
vocab.json
tokenizer/tokens.json
tokens.json
```

Transformers processorでは `tokenizer/`, `processor/`, candidate rootにある既知configを探索します。

配置が曖昧な場合だけ `tokenizer` を明示してください。

## Candidate lifecycle

```text
artifact export
    ↓
finalize_candidate_variant()
    ↓
minimal metadata.json生成
    ↓
ONNX/tokenizer inspection
    ↓
runtime contract validation
    ↓
hf-push-candidate.sh
    ↓
全variantを再検証
    ↓
Central Allocatorでcandidate ID採番
    ↓
candidates/<candidate-id>/へupload
```

採番後も `metadata.json` は書き換えません。candidate IDの正本はBucket directory名です。

取得時:

```text
hf-fetch-candidate.sh
    ↓
.candidate-id をlocal candidate rootへmaterialize
```

これにより、同じminimal metadataをlocal export時とBucket取得後の両方で使えます。

## Generated provenance

評価時には `CandidateArtifacts.provenance_dict()` が次を生成し、`run-context.json`へsnapshotします。

```text
candidate_id
profile_set
variant
resolved profile
decoder
artifact contract
catalog fingerprint
artifact path / SHA-256 / size
variant bundle SHA-256
tokenizer identity
resolved runtime contract
features
```

これらは再現性のため必要ですが、人間入力ではありません。

## Compatibility

次はサポートしません。

```text
candidate metadata schema v1/v2
旧verbose schema v3
runtime-contract.json の手書き
metadata.json 内の candidate_id / catalog SHA / hash / bindings
```

入力形式を一つに固定し、人間が同期しなければならない情報を増やさないことを優先します。
