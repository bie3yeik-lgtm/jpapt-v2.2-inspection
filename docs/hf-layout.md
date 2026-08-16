# Hugging Face Bucket構造

## 目的

Hugging Face Bucketは、model開発・評価中に増えるmutableな履歴を保存する場所です。検証済みartifactを公開するHF Model Repoとは役割を分けます。

```text
HF Bucket      = 開発・実験・評価履歴
HF Model Repo  = promotion済みartifact
GitHub         = source/config/schema/workflow
```

この構造はNeMo/Transformers共通です。

## Canonical tree

```text
hf://buckets/<namespace>/<bucket>/
├── config/
│   ├── current.json
│   └── versions/
│       └── config-NNNNNN/
│           ├── reference.json
│           ├── evaluation-schema.json
│           └── datasets-lock.json
├── experiments/
│   └── <prefix>-NNNNNN/
│       └── README.md
├── candidates/
│   └── <prefix>-NNNNNN/
│       ├── README.md
│       ├── metadata.json
│       └── <artifacts>
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

`ctc/`、`tdt/`、`whisper/`、`nemo/`、`transformers/`をtop-level分類にはしません。これらはmetadata/configで表現します。

## `config/`

### `current.json`

現在使用するimmutable config versionへのpointerです。

```json
{
  "schema_version": 1,
  "config_version": "config-000002"
}
```

### `versions/config-NNNNNN/`

1 versionは3つのrevision文書の集合です。

```text
reference.json
evaluation-schema.json
datasets-lock.json
```

公開済みversionは上書きしません。どれか1つでも変更したら新しい`config-NNNNNN`を作ります。

通常実行は`current.json`を参照し、再現時は`HF_CONFIG_VERSION`で過去versionを直接指定できます。

## `reference.json`

共通identity:

```text
development_artifact
upstream
tokenizer
reference
decoders
```

Bucket名は記録しません。Bucketはrouting情報です。

## `experiments/`

論理的な試行・評価単位です。

```text
cpu-full-eval-000002
cross-platform-parity-000003
graph-optimization-000004
```

prefixは説明用、6桁suffixは機械管理です。

## `candidates/`

正式評価対象になったartifactを保存します。

### 単一graph例

```text
candidates/parakeet-ctc-candidate-000002/
  README.md
  metadata.json
  model.onnx
  vocabulary.json
```

### 複数graph例

```text
candidates/whisper-candidate-000003/
  README.md
  metadata.json
  encoder.onnx
  decoder.onnx
  decoder_with_past.onnx
  tokenizer/
```

frameworkによってtreeの階層を変えず、artifact roleを`metadata.json`で識別します。

## 自動採番

CandidateとExperimentは次の形式です。

```text
<prefix>-NNNNNN
```

採番はprefixごとではなくcollection全体で行います。

```text
最大既存suffix + 1
```

`000001`を構造例として置いている場合、最初の実運用IDは自動的に`000002`になります。

採番後すぐ`README.md`を作成し、object storage上でpathを実体化するとともに用途を記録します。

## `reference/`

canonical frameworkから生成した比較用assetを保存します。

```text
manifests/
outputs/
tensors/
metadata/
```

大容量tensorやaudioをGitへ入れず、必要なreference artifactをBucketへ置きます。

## `runs/`

1回の具体的なexecutionです。連番にはしません。

```text
runs/<run-id>/
```

`run-context.json`にはcandidate、experiment、config version、HF routing snapshot、provider、host、Git revision等を保存します。

## `benchmarks/`

frameworkではなく実行環境で分類します。

```text
benchmarks/<candidate-id>/
  linux-cpu/
  linux-cuda/
  windows-cpu/
  windows-cuda/
  windows-directml/
  macos-cpu/
  macos-coreml/
```

実行していないdirectoryを作る必要はありません。

## `scripts/`と`tmp/`

`tmp/`は破棄可能です。`scripts/`はBucket側に履歴として必要な補助materialを置くための領域であり、source codeの正本はGitです。

## Model Repoとの関係

```text
Candidate
  ↓
Evaluation
  ↓
Acceptance
  ↓
Promotion
  ↓
HF Model Repo
```

`development_artifact.repo_id`はModel Repoを指し、Bucketを指しません。

## Routing

現在のBucket割当は`HF_TARGETS_JSON`で管理します。同一snapshot内では`HF_BUCKET`は一意ですが、将来の容量・用途変更でtargetのBucketを変更できます。過去runは当時のBucketをrun-contextに保存します。

詳細は`docs/hf-bucket-operations.md`と`docs/hf-routing-snapshots.md`を参照してください。