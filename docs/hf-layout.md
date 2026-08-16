# Hugging Face Bucket構造

## 目的

Hugging Face Bucketはmodel開発・評価中に増えるmutableな履歴を保存する場所です。検証済みartifactを公開するHF Model Repoとは役割を分けます。

```text
HF Bucket      = 開発・実験・評価履歴
HF Model Repo  = promotion済みartifact
GitHub         = source/config/schema/workflow
```

この構造はNeMo/Transformers共通です。

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

## ルート`README.md`

BucketルートのREADMEは人間向け説明と中央Allocatorの状態表示を兼ねます。

Allocatorが管理するのは次のmarker内だけです。

```html
<!-- hf-central-allocator:start -->
...
<!-- hf-central-allocator:end -->
```

ここには:

```text
直近採番
candidates最大番号
experiments最大番号
config最大番号
最終更新時刻
```

が自動記録されます。marker外の説明は保持されます。

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

```text
README.md               中央Allocatorによる番号予約・provenance
reference.json          model/reference identity
 evaluation-schema.json 評価rule identity
 datasets-lock.json      dataset revision lock
```

canonical revision bundleは3 JSONで、READMEは採番履歴です。

公開済みversionは上書きしません。どれか1つでも変更したら中央Allocatorで新しい`config-NNNNNN`を発行します。

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

prefixは説明用、6桁suffixは中央Allocatorが管理します。

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

対象:

```text
candidates
experiments
config/versions
```

形式:

```text
<prefix>-NNNNNN
config-NNNNNN
```

採番はprefixごとではなくcollection全体で行います。

```text
最大既存suffix + 1
```

複数Repositoryが同じBucketを扱う場合も、本Repositoryの中央Allocatorを唯一の採番点とします。各Repositoryが独自に`max+1`を計算してはいけません。

`000001`を構造例として置いている場合、最初の実運用IDは`000002`になります。

採番後すぐ各ID直下へ`README.md`を作成し番号を予約します。後続publishが失敗してもその番号は再利用しません。

詳細は [`central-allocator.md`](./central-allocator.md) を参照してください。

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

関連文書:

```text
docs/central-allocator.md
docs/hf-bucket-operations.md
docs/hf-routing-snapshots.md
```
