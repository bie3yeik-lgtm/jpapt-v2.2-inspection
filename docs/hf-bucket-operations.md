# Hugging Face Bucket共通運用仕様

## 目的

この文書は、本リポジトリで採用するHF Bucket運用を他のmodel開発Repositoryにも移植できる形で定義します。NeMo/Transformers、CTC/TDT/Whisperなどのmodel差分には依存しません。

## 1. 保存先の役割

```text
GitHub Repository
  source / config / schema / workflow / docs

HF Bucket
  mutable development / experiment / evaluation history

HF Model Repo
  validated development/release artifact
```

Bucketをcanonical model identityにはしません。

## 2. Canonical tree

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
├── benchmarks/
│   └── <candidate-id>/
│       └── <environment-provider>/
├── scripts/
└── tmp/
```

Framework/decoder/provider名はtop-level treeを分岐させず、metadataで保持します。

## 3. Routing

GitHub ActionsではRepository Variableを使います。

```text
HF_TARGETS_JSON
```

例:

```json
{
  "model-a": {
    "HF_BUCKET": "owner/bucket-a",
    "HF_MODEL_REPO": "owner/model-a"
  },
  "model-b": {
    "HF_BUCKET": "owner/bucket-b",
    "HF_MODEL_REPO": "owner/model-b"
  }
}
```

### 現在snapshotのルール

```text
target IDは一意
HF_BUCKETは一意
各targetにHF_BUCKET/HF_MODEL_REPOが1つ
```

### 時系列のルール

Bucket割当は将来変更できます。

```text
T1: model-a -> bucket-a
T2: model-a -> bucket-c
```

これは正常です。過去runはrun-contextに保存された当時のroutingを使います。

## 4. Versioned Config

`config/revisions/`を上書きしません。

```text
config/current.json
  ↓
config/versions/config-NNNNNN/
```

`current.json`:

```json
{
  "schema_version": 1,
  "config_version": "config-000002"
}
```

各versionはimmutableです。

```text
reference.json
evaluation-schema.json
datasets-lock.json
```

どれかを変更する場合は新versionを発行します。

## 5. Config versionのpublish

推奨script:

```bash
bash scripts/hf/hf-push-config-version.sh <local-config-dir>
```

処理順:

```text
local 3 JSONをstrict validation
  ↓
次のconfig-NNNNNNを決定
  ↓
version directoryへupload
  ↓
全file成功確認
  ↓
最後にconfig/current.json更新
```

`current.json`を先に変更して、不完全なversionを指さないことが重要です。

## 6. Configの取得

通常:

```bash
bash scripts/hf/hf-fetch-revisions.sh
```

過去version:

```bash
HF_CONFIG_VERSION=config-000023 \
  bash scripts/hf/hf-fetch-revisions.sh
```

ローカル解決結果:

```text
.ci/hf/config/
  resolved.json
  revisions/
```

Runには`config_version`とrevision bundle hashを保存します。

## 7. Candidate / Experiment自動採番

形式:

```text
<prefix>-NNNNNN
```

数値suffixはprefixごとではなくcollection全体で管理します。

例:

```text
experiments/
  cpu-full-eval-000002
  graph-optimization-000003
  rust-eval-000007
```

次にどのprefixを使ってもsuffixは`000008`です。

### 採番アルゴリズム

```text
collectionをrecursive list
  ↓
path先頭componentの末尾6桁を抽出
  ↓
最大値を取得
  ↓
+1
  ↓
<prefix>-NNNNNN
```

`000001`が構造例として存在すれば最初の実運用値は`000002`になります。

## 8. READMEによる予約

Object storageには空directoryがないため、採番直後に次を作ります。

```text
<allocated-id>/README.md
```

READMEには少なくとも次を記録します。

```text
collection
bucket
prefix
sequence
allocated_at
target_id
candidate_id
evaluation_id
provider_id
GitHub run metadata
```

これにより番号の意味を人間が確認でき、pathも実体化されます。

## 9. Race condition

単純な`list → max+1 → write`は同時実行に弱いため、GitHub Actionsではallocator jobだけをBucket単位で直列化します。

```yaml
concurrency:
  group: hf-experiment-id-${{ inputs.hf_bucket }}
  cancel-in-progress: false
```

他Repositoryへ移植するときも、同じBucket/collectionへ採番するworkflow間で同じconcurrency naming policyを使ってください。

## 10. Candidate lifecycle

ローカルexportでは正式番号を持たなくても構いません。

```text
candidate_id = unallocated
```

Bucket publish時:

```bash
bash scripts/hf/hf-push-candidate.sh ./local-candidate [prefix]
```

処理:

```text
ID自動採番
README予約
metadata.jsonのcandidate_id更新
artifact upload
```

既存candidateを評価するときはcandidate IDを明示指定します。これは採番ではなくartifact selectionです。

## 11. Experiment lifecycle

Experimentは1つ以上のrunを束ねる論理単位です。

```text
cpu-full-eval-NNNNNN
cross-platform-parity-NNNNNN
rust-eval-NNNNNN
```

Cross-platform matrixでは全jobが同じexperiment IDを共有します。

## 12. Run lifecycle

Run IDは連番にしません。1 concrete executionを一意に識別します。

Runに保存すべき情報:

```text
candidate ID / artifact SHA-256
experiment ID
config version
revision bundle
HF routing snapshot
Git revision
host / architecture
runtime / provider
evaluation suite
```

## 13. Benchmark lifecycle

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

Framework名ではなく実行環境を分類軸にします。

## 14. `reference.json`

共通provenance:

```text
development_artifact  HF Model Repo snapshot
upstream              source model snapshot
tokenizer             tokenizer/processor snapshot
reference             canonical implementation
decoders              decoder contract
```

`HF_BUCKET`は書きません。

## 15. 過去runの再現

現在の`HF_TARGETS_JSON`を過去runへ適用しません。

参照するもの:

```text
run-context.metadata.hf_bucket
run-context.revisions.config_version
run-context.artifact.candidate_id
run-context.metadata.experiment_id
```

その後artifact SHAとrevision bundle hashを照合します。

## 16. 他Repositoryへ移植する最低構成

```text
scripts/ci/next-hf-sequence-id.py
scripts/hf/hf-allocate-id.sh
scripts/hf/hf-push-candidate.sh
scripts/hf/hf-push-config-version.sh
scripts/hf/hf-fetch-revisions.sh
scripts/hf/hf-fetch-candidate.sh
scripts/ci/validate-revisions.py
```

Repository settings:

```text
Secret: HF_TOKEN
Variable: HF_TARGETS_JSON
```

## 17. 不変条件

```text
既存config-NNNNNNを上書きしない
candidate/experiment suffixを再利用しない
prefixは説明用でcounterを所有しない
採番直後にREADMEを作る
過去candidateを明示的に再評価できる
通常実行はcurrent.jsonに従う
過去再現はHF_CONFIG_VERSIONで固定できる
reference.jsonへHF_BUCKETを書かない
runとexperimentを別identityにする
通常PR CIをmutable remote Bucketに依存させない
現在HF_TARGETS_JSON内のHF_BUCKETは一意
routingの歴史的変更を許容する
```

この運用により、frameworkが増えてもstorage lifecycleを変更せずに拡張できます。