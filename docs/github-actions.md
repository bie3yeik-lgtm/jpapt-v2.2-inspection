# GitHub Actions運用

## 基本設定

必須Secret:

```text
HF_TOKEN
```

中央Allocatorを他Repositoryから利用する場合のSecret:

```text
HF_ALLOCATOR_GITHUB_TOKEN
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

## 主要workflow

```text
Validate HF Layout
HF Central Sequence Allocator
CPU Full Evaluation
Cross Platform ONNX Parity
Rust Cross Platform Evaluation
```

`HF Central Sequence Allocator`は直接人間が番号を決めるためのworkflowではなく、他のworkflow/scriptから呼ばれる中央採番サービスです。

## Target解決

`scripts/ci/resolve-hf-target.py`が次を解決します。

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

現在snapshot内のBucket重複は不正です。過去snapshotとの割当変更は許容します。

GitHub ActionsはRepository Variableから`workflow_dispatch`のchoice一覧を動的生成できないため、`hf_bucket`はstring inputです。実行時に`HF_TARGETS_JSON`と照合します。

## Versioned Config

正規経路:

```text
config/current.json
  ↓
config/versions/config-NNNNNN/
  ↓
reference.json
evaluation-schema.json
datasets-lock.json
```

`hf-fetch-revisions.sh`が選択versionを`.ci/hf/config/revisions/`へmaterializeし、`.ci/hf/config/resolved.json`へ解決結果を保存します。

過去versionの再現:

```text
HF_CONFIG_VERSION=config-000023
```

新しい`config-NNNNNN`の番号も中央Allocatorが発行します。

## Central Sequence Allocator

採番対象:

```text
candidates
experiments
config
```

公開入口:

```text
scripts/hf/hf-request-id.sh
scripts/hf/hf-allocate-id.sh  # 通常実行では中央clientへ転送
```

中央workflowだけが実際の:

```text
list -> max suffix + 1 -> README reservation
```

を実行します。

### グローバル排他

複数Repositoryが同じBucketを利用してもraceしないよう、中央Allocator Repository上でBucket単位に直列化します。

```yaml
concurrency:
  group: hf-central-sequence-${{ inputs.hf_bucket }}
  cancel-in-progress: false
```

評価workflow側に個別の採番concurrencyを置く必要はありません。

### 認証

このRepository内部のworkflowでは:

```yaml
GH_TOKEN: ${{ secrets.HF_ALLOCATOR_GITHUB_TOKEN || github.token }}
```

を使います。

別Repositoryから中央Allocatorを呼ぶ場合は、中央Repositoryへworkflow dispatch/read・artifact readできる `HF_ALLOCATOR_GITHUB_TOKEN` を呼出元に設定します。

### BucketルートREADME更新

中央Allocatorは採番後にBucketルートの:

```text
README.md
```

へmanaged blockを更新します。

記録内容:

```text
最終更新時刻
直近の採番ID
candidatesの現在最大番号
experimentsの現在最大番号
configの現在最大番号
```

番号は「publish成功済み最大値」ではなく「Allocatorが予約した最大値」です。採番後の処理が失敗しても番号は再利用しません。

詳細は [`central-allocator.md`](./central-allocator.md) を参照してください。

## Validate HF Layout

### PR / push

remote Bucketに依存せずRepository内だけを検証します。

```text
source-controlled config
schema
scripts shell syntax
synthetic revision fixture
sequence allocator unit test
evaluator capability unit test
```

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

## Evaluator capability

workflowは `EXPECTED_DECODER == ctc` のようなarchitecture固有条件を直接持ちません。

能力宣言:

```text
config/evaluators/python-onnx.toml
config/evaluators/rust-onnx.toml
```

検証:

```text
scripts/ci/validate-evaluator-capability.py
```

実行フロー:

```text
target解決
  ↓
EXPECTED_DECODER
  ↓
evaluator capability validation
  ↓
evaluation runtime
```

現在はPython/Rustとも`ctc`のみをsupported decoderとして宣言しています。TDTやWhisper autoregressive実装を追加するときは、workflowへ条件式を追加せずcapability定義とruntime adapterを拡張します。

## Candidate ID

評価workflowの`candidate_id` inputは残します。これは採番ではなく、既存のどのimmutable candidateを評価するかを指定するためです。

新規candidate:

```text
hf-push-candidate.sh
  -> central allocator
  -> candidate ID reservation
  -> artifact upload
```

## CPU Full Evaluation

```text
existing candidateを指定
  ↓
central allocatorでexperiment ID発行
  ↓
target/config version解決
  ↓
revision validation
  ↓
python-onnx capability validation
  ↓
candidate/reference取得
  ↓
Linux CPU full evaluation
  ↓
run + benchmark upload
```

## Cross Platform ONNX Parity

1 workflow runに1つの`cross-platform-parity-NNNNNN`を中央Allocatorで発行し、matrix全体で共有します。

```text
Linux CPU
Windows CPU
macOS CPU
macOS CoreML
```

各matrix jobは独立run IDを持ちます。

## Rust Cross Platform Evaluation

1つの`rust-eval-NNNNNN`を中央Allocatorで発行します。Rust evaluatorのdecoder対応可否も`rust-onnx` capability contractで検証します。

## Rust CI / Release

`rust-ci.yml`はHF storage routingとは独立したcompile/test workflowです。

`rust-release.yml`もHF Model Repoへのpromotionとは別で、Rust binaryのGitHub Releaseを担当します。

## Routing変更後の過去run

現在の`HF_TARGETS_JSON`から過去runのBucketを推測しません。

```text
run-context.metadata.hf_bucket
run-context.metadata.hf_target_id
run-context.metadata.hf_model_repo
run-context.revisions.config_version
```

を使います。

関連文書:

```text
docs/central-allocator.md
docs/hf-routing-snapshots.md
docs/hf-bucket-operations.md
```
