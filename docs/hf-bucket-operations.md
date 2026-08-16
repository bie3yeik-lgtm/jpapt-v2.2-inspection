# Hugging Face Bucket共通運用仕様

## 目的

この文書は、本リポジトリで採用するHF Bucket運用を他のmodel開発Repositoryにも移植できる形で定義します。NeMo/Transformers、CTC/TDT/Whisperなどのmodel差分には依存しません。

採番実装の詳細は [`central-allocator.md`](./central-allocator.md) を参照してください。

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
├── benchmarks/
│   └── <candidate-id>/
│       └── <environment-provider>/
├── scripts/
└── tmp/
```

Framework/decoder/provider名はtop-level treeを分岐させず、metadataで保持します。

Bucketルート`README.md`には人間向け説明に加え、中央Allocatorが管理する現在番号blockを保持します。

## 3. Routing

GitHub ActionsではRepository Variableを使います。

```text
HF_TARGETS_JSON
```

同一snapshot内では:

```text
target IDは一意
HF_BUCKETは一意
各targetにHF_BUCKET/HF_MODEL_REPOが1つ
```

ただしBucket割当は将来変更できます。

```text
T1: model-a -> bucket-a
T2: model-a -> bucket-c
```

過去runはrun-contextに保存された当時のrouting snapshotを使います。

## 4. Versioned Config

revision文書は上書きしません。

```text
config/current.json
  ↓
config/versions/config-NNNNNN/
```

各versionはimmutableです。

```text
README.md
reference.json
evaluation-schema.json
datasets-lock.json
```

`README.md`は中央Allocatorが番号予約時に作成します。canonical revision bundleは3 JSONです。

## 5. Config versionのpublish

```bash
bash scripts/hf/hf-push-config-version.sh <local-config-dir>
```

処理順:

```text
local 3 JSONをstrict validation
  ↓
中央Allocatorへconfig version要求
  ↓
config-NNNNNN/README.md予約
  ↓
3 JSON upload
  ↓
全file成功確認
  ↓
最後にconfig/current.json更新
```

採番後のuploadが失敗しても番号は再利用しません。また`current.json`は未完成versionを指しません。

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

Runには`config_version`とrevision bundle hashを保存します。

## 7. 中央自動採番

対象:

```text
candidates   <prefix>-NNNNNN
experiments  <prefix>-NNNNNN
config       config-NNNNNN
```

数値suffixはprefixごとではなくcollection全体で管理します。

```text
experiments/
  cpu-full-eval-000002
  graph-optimization-000003
  rust-eval-000007
```

次にどのprefixを使ってもsuffixは`000008`です。

採番要求は全Repositoryから本リポジトリの:

```text
.github/workflows/hf-central-allocator.yml
```

へ集約します。

## 8. Race conditionと排他

以前の「各Repositoryで`list -> max+1`し、各Repoのconcurrencyで守る」方式は採用しません。GitHub ActionsのconcurrencyはRepositoryをまたいだglobal lockではないためです。

現在は中央Allocator RepositoryのworkflowでBucket全体を直列化します。

```yaml
concurrency:
  group: hf-central-sequence-${{ inputs.hf_bucket }}
  cancel-in-progress: false
```

したがってRepo A/B/Cが同じBucketを利用しても採番実行点は1つです。

## 9. READMEによる予約

採番直後に:

```text
<allocated-id>/README.md
```

を書きます。

READMEには:

```text
collection
bucket
prefix
sequence
allocated_at
source_repository
target_id
candidate_id
evaluation_id
provider_id
GitHub run metadata
```

など、呼出時に得られるprovenanceを記録します。

予約後に後続処理が失敗しても番号は欠番として残し、再利用しません。

## 10. BucketルートREADME

中央Allocatorは採番のたびに:

```text
hf://buckets/<namespace>/<bucket>/README.md
```

のmanaged blockを更新します。

```html
<!-- hf-central-allocator:start -->
...
<!-- hf-central-allocator:end -->
```

記録内容:

```text
直近採番
candidates 現在最大番号
experiments 現在最大番号
config 現在最大番号
最終更新時刻
```

marker外の人間向け説明は保持します。

## 11. 中央Allocator client

通常入口:

```text
scripts/hf/hf-request-id.sh
```

互換入口:

```text
scripts/hf/hf-allocate-id.sh
```

通常の`hf-allocate-id.sh`呼出は中央clientへ転送されます。低レベル採番は`HF_ALLOCATOR_INTERNAL=1`を設定する中央workflowだけが実行します。

### 他Repositoryからの認証

呼出元Repositoryに:

```text
HF_ALLOCATOR_GITHUB_TOKEN
```

を設定します。中央Allocator Repositoryに対してworkflow dispatch/readとartifact readが可能なtokenを使用します。

## 12. Candidate lifecycle

ローカルexport時は:

```text
candidate_id = unallocated
```

で構いません。

Bucket publish:

```bash
bash scripts/hf/hf-push-candidate.sh ./local-candidate [prefix]
```

処理:

```text
中央AllocatorでID予約
metadata.jsonのcandidate_id更新
artifact upload
```

既存candidateを評価するときはcandidate IDを明示指定します。これは採番ではなくartifact selectionです。

## 13. Experiment lifecycle

Experimentは1つ以上のrunを束ねる論理単位です。

```text
cpu-full-eval-NNNNNN
cross-platform-parity-NNNNNN
rust-eval-NNNNNN
```

Cross-platform matrixでは全jobが同じexperiment IDを共有します。

## 14. Run lifecycle

Run IDは連番にしません。

保存すべき情報:

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

## 15. Benchmark lifecycle

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

## 16. Evaluator capability

Storage lifecycleとruntime capabilityを混同しません。

```text
config/evaluators/<evaluator>.toml
  ↓
validate-evaluator-capability.py
```

workflowは`ctc`や`whisper_autoregressive`を直接条件分岐せず、選択targetのdecoderが利用するevaluatorで実行可能かだけを検証します。

## 17. `reference.json`

共通provenance:

```text
development_artifact  HF Model Repo snapshot
upstream              source model snapshot
tokenizer             tokenizer/processor snapshot
reference             canonical implementation
decoders              decoder contract
```

`HF_BUCKET`は書きません。

## 18. 過去runの再現

現在の`HF_TARGETS_JSON`を過去runへ適用しません。

```text
run-context.metadata.hf_bucket
run-context.revisions.config_version
run-context.artifact.candidate_id
run-context.metadata.experiment_id
```

を参照し、artifact SHAとrevision bundle hashを照合します。

## 19. 他Repositoryへ移植する最低構成

中央Allocator Repository側:

```text
.github/workflows/hf-central-allocator.yml
scripts/ci/next-hf-sequence-id.py
scripts/hf/hf-allocate-id.sh
scripts/hf/hf-update-root-readme.sh
```

呼出Repository側:

```text
scripts/hf/hf-request-id.sh
scripts/hf/hf-push-candidate.sh
scripts/hf/hf-push-config-version.sh
scripts/hf/hf-fetch-revisions.sh
scripts/hf/hf-fetch-candidate.sh
```

Settings:

```text
HF_TOKEN
HF_TARGETS_JSON
HF_ALLOCATOR_GITHUB_TOKEN  # cross-repository caller
```

## 20. 不変条件

```text
既存config-NNNNNNを上書きしない
candidate/experiment/config suffixを人間が決めない
予約済みsuffixを再利用しない
prefixは説明用でcounterを所有しない
全Repositoryの採番を中央Allocatorへ集約する
採番直後にREADMEを作る
BucketルートREADMEのmanaged blockをAllocatorが更新する
過去candidateを明示的に再評価できる
通常実行はcurrent.jsonに従う
過去再現はHF_CONFIG_VERSIONで固定できる
reference.jsonへHF_BUCKETを書かない
runとexperimentを別identityにする
通常PR CIをmutable remote Bucketに依存させない
現在HF_TARGETS_JSON内のHF_BUCKETは一意
routingの歴史的変更を許容する
```

この運用により、framework・runtime・Repository数が増えてもstorage lifecycleと採番規則を変更せず拡張できます。
