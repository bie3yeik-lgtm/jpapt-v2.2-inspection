# Hugging Face Bucket構造

## 目的

Hugging Face Bucketはmodel開発・実験・評価履歴を保存します。検証済みartifactを公開するHF Model Repoとは役割を分けます。

```text
HF Bucket      開発・実験・評価履歴
HF Model Repo  promotion済みartifact
GitHub         source/schema/workflow/catalog
```

NeMo/Transformers、CTC/TDT/WhisperでBucket top-level treeは変えません。

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
│   └── <allocator-prefix>-NNNNNN/
│       └── README.md
├── candidates/
│   └── <allocator-prefix>-NNNNNN/
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

framework/decoderをBucket rootのdirectory分類にしません。

---

# Git側の2つの中央catalog

## Allocation catalog

```text
config/hf-allocation-catalog.json
```

管理対象:

```text
candidate prefix
experiment prefix
config prefix
```

## ASR runtime catalog

```text
config/asr-catalog.json
```

管理対象:

```text
decoder profile
artifact contract
required/optional artifact roles
tokenizer kind
runtime features
profile set / runtime variant
```

採番名を変更してもruntime catalog SHAが変化しないよう、2つは分離します。

詳細は [`json-contract-design.md`](./json-contract-design.md) を参照してください。

---

# Bucket root README

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
last allocation
candidates reserved maximum
experiments reserved maximum
config reserved maximum
updated timestamp
```

marker外の人間向け説明は保持します。

---

# config/

## current.json

現在利用するimmutable config versionへのmutable pointerです。

```json
{
  "schema_version": 1,
  "config_version": "config-000002",
  "bundle_sha256": "<BUNDLE_SHA256>",
  "updated_at": "..."
}
```

## versions/config-NNNNNN/

新規configは4 JSONです。

```text
reference.json          model/reference/tokenizer provenance
evaluation-schema.json  evaluation rule/schema
datasets-lock.json       dataset provenance
runtime.json             runtime catalog snapshot + profile_set
```

### runtime.json

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

`reference.json`と`evaluation-schema.json`にはdecoder一覧を記述しません。

CTC/TDTはprofile setから導出し、実行時に`runtime_variant`で選択します。

旧3-file configは過去履歴の読み取り互換のみです。

---

# candidates/

新規candidateは`metadata.json schema_version=3`です。

## Parakeet CTC + TDT

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

metadataは、

```text
catalog fingerprint
profile_set
variants.ctc artifact/binding
variants.tdt artifact/binding
```

だけを保持します。

以下は書きません。

```text
variants.ctc.profile
variants.tdt.profile
decoder
artifact_contract
features
tokenizer kind
```

これらは`profile_set + variant`からASR runtime catalogで導出します。

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

workflowはraw prefixを持ちません。

```text
experiment.cpu_full
    ↓ hf-allocation-catalog.json
cpu-full-eval
```

---

# runs/

1回の具体的executionで、連番にはしません。

新規`run-context.json`はschema v2です。

```text
revisions.runtime
  runtime.json SHA
  ASR runtime catalog id/SHA
  profile_set

metadata.candidate
  selected variant
  resolved profile
  decoder
  artifact contract
  selected variant bundle SHA

metadata
  experiment ID
  HF routing snapshot
```

`revisions.reference`と`revisions.evaluation_schema`へdecoder listを再複製しません。

---

# benchmarks/

framework/decoderではなく実行環境/provider軸で保存します。

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

実行していないdirectoryは不要です。

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

NeMo/Transformersでroot構造を分けません。

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

prefixは`config/hf-allocation-catalog.json`から解決します。

詳細は [`central-allocator.md`](./central-allocator.md) を参照してください。

---

# Routing

```text
現在のtarget -> Bucket/Model Repo    HF_TARGETS_JSON
採番policy                           hf-allocation-catalog.json
runtime semantics                   asr-catalog.json
config snapshot                     config-NNNNNN
execution snapshot                  run-context.json
```

同一`HF_TARGETS_JSON` snapshot内では`HF_BUCKET`は一意ですが、将来の容量・用途変更でtargetのBucket割当を変更できます。

---

# Model Repoとの関係

```text
Candidate variant
  ↓ Evaluation
Acceptance
  ↓ Promotion
HF Model Repo
```

promotionではrun-contextに保存されたselected variant bundle identityを再検証します。
