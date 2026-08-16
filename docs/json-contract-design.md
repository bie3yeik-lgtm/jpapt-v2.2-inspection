# JSON Contract 正規化設計

## 目的

同じ意味を複数のJSON/TOML/Workflowへコピーしません。値は次の基準で配置します。

```text
複数candidate/config/runで再利用する意味・policy
    -> Git側の中央catalog

特定snapshot/artifact/exportでしか確定できない事実
    -> そのsnapshot固有JSON

実行時に解決した結果
    -> run-context.jsonへsnapshot
```

中央化の目的は文字数削減ではなく、同期漏れを構造的に無くすことです。

---

## Source of Truthの4層

```text
1. 採番policy
   config/hf-allocation-catalog.json

2. ASR deployment runtime semantics
   config/asr-catalog.json

3. immutable operational snapshot
   config/versions/config-NNNNNN/*.json
   candidates/<candidate-id>/metadata.json

4. execution snapshot
   runs/<run-id>/run-context.json
```

### 重要な分離

採番prefixとASR runtime semanticsは別catalogです。

```text
cpu-full-evalという名前を変更
    !=
CTC/TDT runtime contractを変更
```

両者を同じcatalogへ置くとprefix変更だけでruntime catalog SHAが変わるため分離します。

---

# HF allocation catalog

```text
config/hf-allocation-catalog.json
```

唯一の責務はsemantic allocation keyから表示prefixを解決することです。

```json
{
  "schema_version": 1,
  "catalog_id": "hf-allocation-catalog-v1",
  "prefixes": {
    "candidate.default": "candidate",
    "candidate.parakeet-tdt-ctc-v1": "parakeet-candidate",
    "candidate.whisper-autoregressive-v1": "whisper-candidate",
    "experiment.cpu_full": "cpu-full-eval",
    "experiment.cross_platform_parity": "cross-platform-parity",
    "experiment.rust_eval": "rust-eval",
    "config.version": "config"
  }
}
```

Workflow/scriptはraw prefixではなくsemantic keyを渡します。

```text
experiment.cpu_full
    -> cpu-full-eval
    -> cpu-full-eval-000042
```

中央Allocatorの`allocation.json`はallocation catalog id/SHA、prefix key、resolved prefixをsnapshotします。

---

# ASR runtime catalog

```text
config/asr-catalog.json
```

ここにはcandidate間で再利用するruntime semanticsだけを置きます。

```text
decoder
a​​rtifact contract
tokenizer kind
required/optional artifact roles
runtime feature requirements
profile set
variant -> profile mapping
default variant
```

Parakeet例:

```text
parakeet-tdt-ctc-v1
├── ctc -> ctc-v1
├── tdt -> tdt-v1
└── default -> ctc
```

CTC/TDT切替のためにJSONを書き換えません。

```text
ASR_RUNTIME_VARIANT=ctc
ASR_RUNTIME_VARIANT=tdt
```

---

# Target TOML

Targetはdecoder一覧を持ちません。

```toml
schema_version = 2

[target]
id = "parakeet-tdt_ctc-0.6b-ja"
model_id = "parakeet-tdt_ctc-0.6b-ja"

[runtime]
profile_set = "parakeet-tdt-ctc-v1"
```

supported/default decoderはprofile setから導出します。

`config/models/*.toml`にdecoder説明が残る場合、それはupstream architectureの能力説明です。deployment runtime選択のSource of Truthではありません。

---

# Config Version

Canonical configは4ファイルです。

```text
config/versions/config-NNNNNN/
├── reference.json
├── evaluation-schema.json
├── datasets-lock.json
└── runtime.json
```

## reference.json

ここに固定する必然性があるもの:

```text
development artifact repo/revision
upstream repo/revision
tokenizer repo/revision
canonical reference id/revision/framework
```

`decoders`は記述しません。

## evaluation-schema.json

評価schema、threshold、評価規則だけを保持します。decoder一覧は記述しません。

## datasets-lock.json

使用datasetのrepo/revision/subset/split等を固定します。

## runtime.json

runtime semanticsをコピーせず、catalog snapshotとprofile setだけを固定します。

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

`hf-push-config-version.sh`が自動生成するため通常は手書きしません。

---

# Candidate Metadata v3

candidateにはruntime profileの意味を再記述しません。

```json
{
  "schema_version": 3,
  "candidate_id": "parakeet-candidate-000042",
  "catalog": {
    "id": "asr-runtime-catalog-v1",
    "sha256": "<ASR_RUNTIME_CATALOG_SHA256>"
  },
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "artifacts": {},
      "bindings": {},
      "tokenizer": {"path": "tokenizer/vocabulary.json"}
    },
    "tdt": {
      "artifacts": {},
      "bindings": {},
      "tokenizer": {"path": "tokenizer/vocabulary.json"}
    }
  }
}
```

### Candidateに書かない値

```text
decoder
artifact_contract
profile ID
features
tokenizer kind
required artifact roles
```

これらは次から一意に導出します。

```text
catalog pin
+ profile_set
+ variant名
```

### Candidateに残す値

中央化できないartifact固有値です。

```text
artifact path/SHA-256/size
input/output tensor names
blank/bos/eos/prompt token IDs
TDT durations
predictor state names/shapes/dtypes
KV-cache tensor names
processor/tokenizer asset path
```

これらを中央catalogへ移すと、model/export revisionごとの差を表現できなくなります。

---

# run-context.json

run-contextは設定を定義する場所ではなく、実際に解決した結果を保存する場所です。

新規normalized runはschema v2です。

```text
revisions.runtime
  document_sha256
  catalog.id
  catalog.sha256
  profile_set

revisions.reference
  reference/model provenance

revisions.evaluation_schema
  evaluation schema identity
```

`reference`/`evaluation_schema`へdecoder listを再複製しません。

一方、実行時に選択された値はcandidate provenanceとしてsnapshotします。

```text
profile_set
variant
resolved profile
decoder
artifact contract
runtime catalog fingerprint
variant bundle SHA
```

ここでdecoderを記録するのはSource of Truthの重複ではなく、過去runを直接読めるようにする実行結果snapshotです。

---

# Evaluator Capability

runtime catalogとevaluator capabilityは統合しません。

```text
config/asr-catalog.json
    candidate/runtimeが要求する能力

config/evaluators/*.toml
    evaluator実装が提供する能力
```

```text
required capability
        ↓
validate-evaluator-capability.py
        ↑
provided capability
```

意味が逆なので別contractです。

---

# HF_TARGETS_JSON

`HF_TARGETS_JSON`は現在routingだけを持ちます。

```text
current target -> HF_BUCKET / HF_MODEL_REPO
```

```text
現在routing          HF_TARGETS_JSON
採番policy           hf-allocation-catalog.json
runtime semantics    asr-catalog.json
config snapshot      config-NNNNNN
execution snapshot   run-context.json
```

Bucket割当は将来変更可能です。

---

# Legacy Compatibility

過去データは読み取り可能にしますが、新規作成には使いません。

```text
旧config      reference/evaluationにdecodersを持つ3-file形式
旧candidate   metadata schema v1/v2
旧run         run-context schema v1
```

新規書込み:

```text
config       4-file + runtime.json
candidate    metadata schema v3
run-context  schema v2
```

旧JSONを新しい意味へ黙って上書きしません。

---

# 判断表

| 値 | Source of Truth | 中央化理由 / 個別化理由 |
|---|---|---|
| candidate/experiment/config prefix | `hf-allocation-catalog.json` | 採番policyとして共有可能 |
| decoder/profile semantics | `asr-catalog.json` | candidate間で共通 |
| required artifact roles | `asr-catalog.json` | profile contract |
| tokenizer kind | `asr-catalog.json` | profile contract |
| runtime features | `asr-catalog.json` | profile contract |
| targetのprofile set | target TOML | target固有選択 |
| configのprofile set | `runtime.json` | immutable config snapshot |
| artifact path/SHA/size | candidate metadata | artifact固有 |
| tensor names | candidate metadata | export固有 |
| token IDs/state/KV binding | candidate metadata | model/export固有 |
| upstream/reference revision | `reference.json` | provenance固有 |
| evaluation rule/revision | `evaluation-schema.json` | config固有 |
| dataset revision | `datasets-lock.json` | config固有 |
| current config pointer | `config/current.json` | mutable pointer |
| current Bucket routing | `HF_TARGETS_JSON` | operational routing |
| 実行時解決結果 | `run-context.json` | immutable execution snapshot |

新しいJSON fieldを追加するときは、まずこの表と同じ基準で「policyか、snapshot固有factか、execution snapshotか」を判定してください。
