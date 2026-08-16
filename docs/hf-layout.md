# Hugging Face Bucket構造

## 目的

Hugging Face Bucketはmodel開発・評価中に増えるmutableな履歴を保存する場所です。検証済みartifactを公開するHF Model Repoとは役割を分けます。

```text
HF Bucket      = 開発・実験・評価履歴
HF Model Repo  = promotion済みartifact
GitHub         = source/schema/workflow/ASR catalog
```

NeMo/Transformers、CTC/TDT/Whisperでtop-level treeは変えません。

---

## Canonical tree

```text
hf://buckets/<namespace>/<bucket>/
├── README.md
├── config/
│   ├── current.json
│   └── versions/
│       └── config-NNNNNN/
│           ├── README.md
│           ├── reference.json
│           ├── evaluation-schema.json
│           ├── datasets-lock.json
│           └── runtime.json
├── experiments/
│   └── <catalog-resolved-prefix>-NNNNNN/
│       └── README.md
├── candidates/
│   └── <catalog-resolved-prefix>-NNNNNN/
│       ├── README.md
│       ├── metadata.json
│       └── <variant artifacts>
├── reference/
│   ├── manifests/
│   ├── outputs/
│   ├── tensors/
│   └── metadata/
├── runs/
│   └── <run-id>/
│       ├── run-context.json
│       ├── samples.jsonl
│       ├── metrics.json
│       └── promotion.json
├── benchmarks/
│   └── <candidate-id>/
│       └── <environment-provider>/
│           └── <run-id>.json
├── scripts/
└── tmp/
```

`ctc/`、`tdt/`、`whisper/`、`nemo/`、`transformers/`をBucket root分類にはしません。

---

## Git側の中央ASR Catalog

Bucket自身には再利用可能なdecoder semanticsを複製しません。

```text
Git
└── config/asr-catalog.json
```

ここが次のSource of Truthです。

```text
ID prefix
decoder profile
artifact contract
required artifact roles
tokenizer kind
runtime feature requirements
profile set / variant
```

Bucket configは`runtime.json`からこのcatalog snapshotを参照します。

---

## ルートREADME

```text
hf://buckets/<namespace>/<bucket>/README.md
```

中央Allocatorは次のmarker内だけを更新します。

```html
<!-- hf-central-allocator:start -->
...
<!-- hf-central-allocator:end -->
```

記録内容:

```text
直近採番
candidates最大番号
experiments最大番号
config最大番号
最終更新時刻
```

表示番号はpublish成功番号ではなく予約済み最大番号です。

---

# config/

## current.json

mutable pointerです。

```json
{
  "schema_version": 1,
  "config_version": "config-000002",
  "bundle_sha256": "<BUNDLE_SHA256>",
  "updated_at": "..."
}
```

`config_version`がidentityであり、`updated_at`はprovenanceです。

## versions/config-NNNNNN/

normalized configは4 JSONです。

```text
reference.json
    model/reference/tokenizer provenance

evaluation-schema.json
    evaluation policy/schema/threshold

datasets-lock.json
    dataset provenance

runtime.json
    ASR catalog snapshot + profile_set reference
```

### runtime.json

```json
{
  "schema_version": 1,
  "catalog": {
    "id": "asr-catalog-v1",
    "sha256": "<CATALOG_SHA256>"
  },
  "profile_set": "parakeet-tdt-ctc-v1"
}
```

`runtime.json`は`hf-push-config-version.sh`が自動生成します。

新しいnormalized configでは、

```text
reference.json.decoders
evaluation-schema.json.decoders
```

を記述しません。

CTC/TDT等は`profile_set`から導出します。

旧3-file configは読み取り互換のみ維持します。

---

# candidates/

新規candidateはmetadata schema v3です。

## Parakeet CTC + TDT

同じcandidate IDに両方のvariantを保持できます。

```text
candidates/parakeet-candidate-000002/
├── README.md
├── metadata.json
├── tokenizer/
│   └── vocabulary.json
├── ctc/
│   └── model.onnx
└── tdt/
    ├── encoder.onnx
    ├── predictor.onnx
    └── joint.onnx
```

`metadata.json`は、

```text
profile_set = parakeet-tdt-ctc-v1
variants.ctc.profile = ctc-v1
variants.tdt.profile = tdt-v1
```

を持ちます。

CTC/TDTのdecoder名、artifact contract、required role等は中央catalogから導出します。

## Whisper

```text
candidates/whisper-candidate-000003/
├── README.md
├── metadata.json
├── encoder.onnx
├── decoder.onnx
├── decoder_with_past.onnx
└── tokenizer/
```

詳細は [`candidate-metadata.md`](./candidate-metadata.md) を参照してください。

---

# experiments/

論理的な試行単位です。

```text
cpu-full-eval-000002
cross-platform-parity-000003
rust-eval-000004
```

ただしWorkflowはこれらのraw prefix文字列を直接指定しません。

```text
experiment.cpu_full
experiment.cross_platform_parity
experiment.rust_eval
        ↓ ASR Catalog
表示prefix
```

---

# runs/

1回の具体的executionです。連番にしません。

```text
runs/<run-id>/
```

run-contextには少なくとも、

```text
candidate_id
selected runtime_variant
selected runtime profile
selected variant bundle SHA
config_version
runtime catalog fingerprint
experiment_id
HF routing snapshot
provider/environment
Git revision
```

を残します。

同じcandidateのCTC/TDTは別variant bundle identityを持ちます。

---

# benchmarks/

framework/decoderではなく実行環境軸です。

```text
benchmarks/<candidate-id>/
├── linux-cpu/
├── linux-cuda/
├── windows-cpu/
├── windows-cuda/
├── windows-directml/
├── macos-cpu/
└── macos-coreml/
```

実行していないdirectoryを作る必要はありません。

---

# reference/

canonical frameworkから生成した比較用assetです。

```text
reference/
├── manifests/
├── outputs/
├── tensors/
└── metadata/
```

NeMo/Transformersでroot構造は分けません。

---

# scripts/ / tmp/

```text
tmp      破棄可能
scripts  Bucket履歴として必要な補助materialのみ
```

source codeの正本はGitです。

---

# 採番

対象:

```text
candidates
experiments
config/versions
```

数値suffixはcollection全体で共有します。

```text
最大既存suffix + 1
```

prefixは `config/asr-catalog.json.id_prefixes` から解決します。

詳細は [`central-allocator.md`](./central-allocator.md) を参照してください。

---

# Model Repoとの関係

```text
Candidate variant
  ↓
Evaluation
  ↓
Acceptance
  ↓
Promotion
  ↓
HF Model Repo
```

promotionはrun-contextに保存されたruntime variantのbundle SHAを再検証します。

---

# Routing

現在のtarget→Bucket割当は`HF_TARGETS_JSON`で管理します。

```text
Current routing     HF_TARGETS_JSON
Config semantics    runtime.json + catalog SHA
Execution snapshot  run-context.json
```

同一routing snapshot内では`HF_BUCKET`は一意ですが、将来の容量・用途変更で割当を変更できます。

関連文書:

```text
docs/json-contract-design.md
docs/candidate-metadata.md
docs/central-allocator.md
docs/hf-bucket-operations.md
docs/hf-routing-snapshots.md
```
