# JSON Contract 正規化設計

## 原則

JSONは「人間が決める値」と「コードが観測・生成できる値」を分離します。

```text
人間が決めるpolicy / selection
    -> 最小限の入力JSON/TOML

file・Git・catalog・runtimeから取得できる値
    -> コードで生成

過去runの再現に必要な事実
    -> generated snapshotへ保存
```

同じ意味を複数のJSONへ手入力させません。

---

## Human-authored

人間が直接触るJSONは可能な限り少なくします。

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
catalog SHA
artifact SHA / size
decoder / profile / artifact contract
tensor I/O
token IDs
state/KV metadata
```

### Evaluation manifest JSONL

1行の最小形:

```json
{"dataset_id":"jsut-basic5000","count":6,"seed":"smoke-jsut-v1"}
```

長さ制約が必要な場合だけ追加します。

```json
{"dataset_id":"jsut-basic5000","count":6,"seed":"smoke-jsut-v1","min_duration_sec":1.0,"max_duration_sec":15.0}
```

手書きしない値:

```text
schema_version
entry id
selection.strategy = stable_hash
tags
selection / filtersの不要な入れ子
```

entry identityはseedと行位置等からコード側で生成できます。

---

## Generated / locked JSON

次は再現性のため情報量が多くてもよく、人間が手で維持する対象にはしません。

```text
config/versions/config-NNNNNN/reference.json
config/versions/config-NNNNNN/evaluation-schema.json
config/versions/config-NNNNNN/datasets-lock.json
config/versions/config-NNNNNN/runtime.json
runs/<run-id>/run-context.json
runs/<run-id>/samples.jsonl
runs/<run-id>/metrics.json
benchmarks/**/*.json
evaluation/expected/*.json
```

これらはsource/config/artifactを読み取って生成またはlockすることを基本とします。

---

## Source of Truth

```text
採番policy
    config/hf-allocation-catalog.json

ASR runtime semantics
    config/asr-catalog.json

Target routing / profile set
    config/hf-targets/*.toml

人間のcandidate artifact選択
    candidates/<candidate-id>/metadata.json

人間のevaluation sample選択
    evaluation/manifests/*.jsonl

immutable config snapshot
    config/versions/config-NNNNNN/*.json

execution snapshot
    runs/<run-id>/run-context.json
```

---

## Canonical config bundle

3-file legacy bundleは廃止します。

```text
config/versions/config-NNNNNN/
├── reference.json
├── evaluation-schema.json
├── datasets-lock.json
└── runtime.json
```

`runtime.json`は必須です。

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

ただしこれはgenerated lockです。人間にcatalog SHAを入力させません。

`reference.json` / `evaluation-schema.json`へdecoder一覧を複製しません。

---

## ASR runtime catalog

`config/asr-catalog.json`に共有runtime semanticsを集約します。

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

candidate側は`profile_set + variant`だけで参照します。

---

## run-context.json

run-contextは完全なgenerated execution snapshotです。

人間の編集性より、再現性と監査性を優先します。

```text
host / OS / architecture
Git commit
runtime / provider
config bundle identity
catalog fingerprint
selected candidate
resolved profile / decoder
artifact hashes
resolved evaluation configuration
```

ここにderived情報を保存することは重複ではありません。これはSource of Truthではなく、実行時点のsnapshotです。

schema v2のみをcanonicalとし、run-context v1互換は維持しません。

---

## Legacy compatibility

維持しません。

```text
candidate metadata v1/v2        unsupported
3-file config bundle            unsupported
run-context schema v1           unsupported
```

未使用のschemaを温存することで入力形式が複数になる方がリスクが高いためです。

---

## Field追加の判断基準

新しいfieldを追加する前に次を確認します。

```text
1. 人間しか決められないか？
   YES -> human-authored contractへ追加候補

2. file / Git / catalog / model config / runtimeから取得できるか？
   YES -> human-authored contractへ追加しない

3. 過去runの再現に必要か？
   YES -> generated snapshotへ保存

4. 別のSource of Truthに既に存在するか？
   YES -> 再入力させず参照・snapshotする
```

目標は「schemaに情報を詰めること」ではなく、**人間が間違えられる入力欄を最小化すること**です。
