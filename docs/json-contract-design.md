# JSON Contract 正規化設計

## 原則

JSONは「人間が決める値」と「コードが観測・生成できる値」を分離します。

```text
人間が決めるpolicy / selection
    -> 最小入力JSON/TOML

file・Git・catalog・model config・runtimeから取得できる値
    -> コードで生成

過去runの再現に必要な事実
    -> generated snapshotへ保存
```

同じ意味を複数のJSONへ手入力させません。機械が取得できる値を人間入力へ戻すことも行いません。

## Human-authored contracts

### Candidate metadata

```json
{
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "artifacts": {
        "primary": "ctc/model.onnx"
      },
      "tokenizer": "tokenizer/vocabulary.json"
    }
  }
}
```

手書きしない値:

```text
schema_version
candidate_id
catalog id / SHA
artifact SHA / size
decoder / profile / artifact contract / features
tensor I/O
token IDs
state / KV metadata
```

`tokenizer` は既定配置から一意に発見できる場合は省略できます。

### Evaluation manifest JSONL

最小形:

```json
{"dataset_id":"jsut-basic5000","count":6,"seed":"smoke-jsut-v1"}
```

長さ制約が必要な場合だけ追加します。

```json
{"dataset_id":"jsut-basic5000","count":6,"seed":"smoke-jsut-v1","min_duration_sec":1.0,"max_duration_sec":15.0}
```

手書きしません:

```text
schema_version
entry id
selection.strategy = stable_hash
tags
selection / filters wrapper
```

`ManifestLoader` がstable-hash selection、entry ID、filter objectへ展開します。

## Generated / locked contracts

次は人間が直接維持しません。

```text
config/versions/config-NNNNNN/reference.json
config/versions/config-NNNNNN/evaluation-schema.json
config/versions/config-NNNNNN/datasets-lock.json
config/versions/config-NNNNNN/runtime.json
runs/<run-id>/run-context.json
runs/<run-id>/samples.jsonl
runs/<run-id>/metrics.json
runs/<run-id>/promotion.json
benchmarks/**/*.json
evaluation/expected/*.json
```

情報量が多くても問題ありません。これらは再現性・監査性のためのsnapshotです。

## Source of Truth

```text
採番policy
    config/hf-allocation-catalog.json

ASR runtime semantics
    config/asr-catalog.json

Target routing / profile set
    config/hf-targets/*.toml

candidate artifact selection
    metadata.json

evaluation sample selection
    evaluation/manifests/*.jsonl

immutable config snapshot
    config/versions/config-NNNNNN/*.json

execution snapshot
    runs/<run-id>/run-context.json
```

## Candidate derivation pipeline

```text
minimal metadata.json
    +
config/asr-catalog.json
    +
ONNX graphs
    +
tokenizer / generated model config
    ↓
CandidateArtifacts.load()
    ↓
resolved profile / decoder / contract / features
artifact SHA / size
ONNX tensor binding
state / KV binding
token/generation config
    ↓
validate_candidate_runtime_contract()
    ↓
run-context generated provenance
```

Runtime-critical factが一意に取得できない場合は、推測せずvalidation errorにします。

Candidate IDはmetadataの一部ではありません。

```text
local candidate
    candidate directory名

HF Bucket candidate
    candidates/<candidate-id>/ directory名
        ↓ fetch
    .candidate-id
```

`hf-push-candidate.sh` は採番後にmetadataを書き換えません。

## Manifest derivation pipeline

```text
minimal JSONL
    ↓
ManifestLoader
    ↓
internal ManifestEntry
    id = dataset_id + line position
    strategy = stable_hash
    optional duration filter
    ↓
DatasetResolver
    ↓
resolved immutable sample manifest
```

評価コードはhuman JSONLの構造を再実装せず、canonical loaderを使用します。`scripts/dev/doctor.py` も同じloaderで検証します。

## Canonical config bundle

3-file bundleはサポートしません。

```text
config/versions/config-NNNNNN/
├── reference.json
├── evaluation-schema.json
├── datasets-lock.json
└── runtime.json
```

`runtime.json` は必須generated lockです。

```json
{
  "schema_version": 1,
  "catalog": {
    "id": "asr-runtime-catalog-v1",
    "sha256": "<ASR_RUNTIME_CATALOG_SHA256>"
  },
  "profile_set": "parakeet-tdt-ctc-v1"
}
```

`reference.json` / `evaluation-schema.json`へdecoder一覧を複製しません。

## ASR runtime catalog

`config/asr-catalog.json`へ共有runtime semanticsを集約します。

```text
decoder
artifact contract
tokenizer kind
required/optional artifact roles
runtime feature requirements
profile set
variant -> profile mapping
default variant
```

candidate metadataは `profile_set + variant` だけで参照します。

Evaluator capabilityは別contractです。

```text
config/asr-catalog.json
    candidateが要求する能力

config/evaluators/*.toml
    evaluatorが提供する能力

validate-evaluator-capability.py
    required <= provided を検証
```

Candidateが要求するfeatureをmetadataへ書き足すことはできません。

## run-context.json

完全なgenerated execution snapshotです。

```text
host / OS / architecture
Git commit
runtime / provider
config bundle identity
catalog fingerprint
selected candidate
resolved profile / decoder
artifact hashes
resolved candidate runtime contract
resolved evaluation configuration
```

schema v2のみをcanonicalとし、v1互換は維持しません。

## Promotion

promotionはhuman metadataの内容ではなく、評価時に生成されたcandidate provenanceを照合します。

```text
accepted full run
    ↓
run-context metadata.candidate.variant / bundle_sha256
    ↓
Bucket candidate取得
    ↓
.candidate-id materialize
    ↓
CandidateArtifactsで再導出・再hash
    ↓
bundle SHA一致
    ↓
HF Model Repoへpromotion
```

これによりmetadataへhashやcandidate IDを書かなくてもpromotion時のidentityを固定できます。

## Legacy compatibility

維持しません。

```text
candidate metadata v1/v2       unsupported
旧verbose candidate schema     unsupported
手書き runtime-contract.json   unsupported
3-file config bundle           unsupported
run-context schema v1          unsupported
```

## Field追加の判断基準

```text
1. 人間しか決められないか？
   YES -> human-authored contractへ追加候補

2. file / Git / catalog / model config / runtimeから取得できるか？
   YES -> human-authored contractへ追加しない

3. 過去runの再現に必要か？
   YES -> generated snapshotへ保存

4. 別のSource of Truthに既に存在するか？
   YES -> 再入力させず参照またはsnapshotする
```

目標は **人間が間違えられる入力欄を最小化すること** です。
