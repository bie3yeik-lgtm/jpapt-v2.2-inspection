# GitHub Actions運用

## 基本設定

Secret:

```text
HF_TOKEN
```

Repository Variable:

```text
HF_TARGETS_JSON
```

`HF_TARGETS_JSON`は現在時点のstorage routingです。

```json
{
  "target-a": {
    "HF_BUCKET": "owner/bucket-a",
    "HF_MODEL_REPO": "owner/model-a"
  },
  "target-b": {
    "HF_BUCKET": "owner/bucket-b",
    "HF_MODEL_REPO": "owner/model-b"
  }
}
```

同一snapshot内では`HF_BUCKET`は一意です。ただし将来、容量・用途・migrationの都合でroutingを変更できます。

## 手動workflow

現在の主要workflow:

```text
Validate HF Layout
CPU Full Evaluation
Cross Platform ONNX Parity
Rust Cross Platform Evaluation
```

GitHub ActionsはRepository Variableから`workflow_dispatch`のchoice一覧を動的生成できないため、`hf_bucket`はstring inputです。実行時に`HF_TARGETS_JSON`と照合してtargetを解決します。

## Target解決

内部では`scripts/ci/resolve-hf-target.py`が次を解決します。

```text
HF_TARGET_ID
HF_BUCKET
HF_MODEL_REPO
EXPECTED_DEVELOPMENT_REPO_ID
EXPECTED_UPSTREAM_REPO_ID
EXPECTED_TOKENIZER_REPO_ID
EXPECTED_FRAMEWORK
EXPECTED_DECODER
```

現在snapshot内のBucket重複は不正です。過去snapshotとの割当変更は不正ではありません。

## Versioned Config

評価workflowは次を直接読むのではありません。

```text
config/revisions/*.json
```

正規経路は次です。

```text
config/current.json
  ↓
config/versions/config-NNNNNN/
  ↓
reference.json
evaluation-schema.json
datasets-lock.json
```

`hf-fetch-revisions.sh`が選択versionを`.ci/hf/config/revisions/`へmaterializeし、`.ci/hf/config/resolved.json`に解決結果を保存します。

過去versionを再現する場合:

```text
HF_CONFIG_VERSION=config-000023
```

## Validate HF Layout

### PR / push

remote Bucketへ依存せず、Repository内だけを検証します。

```text
source-controlled config
schema
scripts
synthetic revision fixture
ID allocator unit test
```

mutableなHF Bucket状態の問題で通常PR CIを壊さないためです。

### workflow_dispatch

手動実行時だけ実Bucketをstrict validationします。

```text
hf_bucket入力
  ↓
target解決
  ↓
config/current.json
  ↓
selected config version
  ↓
RevisionBundle validation
  ↓
target identity validation
  ↓
required directory validation
```

Required lifecycle collections:

```text
experiments
candidates
reference
runs
benchmarks
scripts
tmp
```

## 自動Experiment採番

評価workflowでは重いevaluation jobの前に短いallocator jobを実行します。

```text
cpu-full-eval-NNNNNN
cross-platform-parity-NNNNNN
rust-eval-NNNNNN
```

採番は`experiments/`全体の最大suffix+1です。

Raceを避けるためallocator jobだけBucket単位で直列化します。

```yaml
concurrency:
  group: hf-experiment-id-${{ inputs.hf_bucket }}
  cancel-in-progress: false
```

重いmatrix jobは採番後に並列実行できます。

## Candidate ID

評価workflowの`candidate_id` inputは残します。

これは「新しい番号を人間が決める」入力ではなく、**既存のどのimmutable candidateを評価するか**を指定するためです。

新規candidateの正式IDは`hf-push-candidate.sh`が自動発行します。

## CPU Full Evaluation

概略:

```text
existing candidateを指定
  ↓
experiment ID自動発行
  ↓
target/config version解決
  ↓
revision validation
  ↓
candidate/reference取得
  ↓
Linux CPU full evaluation
  ↓
run + benchmark upload
```

現行Python evaluatorはCTC中心です。Whisper autoregressive targetはrevision validation後にdecoder compatibility errorとして明示的に停止します。

## Cross Platform ONNX Parity

1 workflow runに1 experiment IDを発行し、matrix全体で共有します。

```text
Linux CPU
Windows CPU
macOS CPU
macOS CoreML
```

各matrix jobは独立run IDを持ちます。

## Rust Cross Platform Evaluation

同様に1つの`rust-eval-NNNNNN`を共有します。

```text
Linux CPU
Windows CPU
macOS CPU
macOS CoreML
```

Rust evaluatorもconfig version、revision identity、routing snapshot、experiment IDをrun-contextへ記録します。

## Rust CI / Release

`rust-ci.yml`はHF storage routingとは独立したcompile/test workflowです。

`rust-release.yml`もHF Bucket/Model Repoのpromotionとは別で、Rust binaryのGitHub Releaseを担当します。

## Routing変更後の過去run

現在の`HF_TARGETS_JSON`から過去runのBucketを推測しません。

```text
run-context.metadata.hf_bucket
run-context.metadata.hf_target_id
run-context.metadata.hf_model_repo
run-context.revisions.config_version
```

を使います。

詳細:

```text
docs/hf-routing-snapshots.md
docs/hf-bucket-operations.md
```