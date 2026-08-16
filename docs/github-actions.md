# GitHub Actions 利用ガイド

本リポジトリのHF連携workflowは、Repository Variable `HF_TARGETS_JSON` を基準にASR targetを解決します。

詳細なBucket運用仕様は `docs/hf-bucket-operations.md` を参照してください。

## Repository settings

Secret:

```text
HF_TOKEN
```

Variable:

```text
HF_TARGETS_JSON
```

例:

```json
{
  "kotoba-whisper-v1.0": {
    "HF_BUCKET": "gawohok7/tf-v1-onnx-dev-bucket",
    "HF_MODEL_REPO": "gawohok7/tf-v1-onnx-dev"
  },
  "parakeet-tdt_ctc-0.6b-ja": {
    "HF_BUCKET": "gawohok7/jpapt-v2.2-dev-bucket",
    "HF_MODEL_REPO": "gawohok7/jpapt-v2.2-dev"
  }
}
```

`HF_BUCKET` はtargetごとに一意でなければなりません。

## HF Bucketを選択するworkflow

次の手動workflowは共通して `hf_bucket` を入力に持ちます。

```text
Validate HF Layout
CPU Full Evaluation
Cross Platform ONNX Parity
Rust Cross Platform Evaluation
```

GitHub ActionsはRepository Variableから`workflow_dispatch`のchoice一覧を動的生成できないため、`hf_bucket`は文字列入力です。実行時に`HF_TARGETS_JSON`と照合し、不明なBucketは拒否します。

```text
hf_bucket
  -> vars.HF_TARGETS_JSON
  -> target id
  -> HF_MODEL_REPO
  -> framework / decoder / model config
```

## Versioned config

Bucketのrevision設定は直下上書きではなく、次の構造を使用します。

```text
config/current.json
config/versions/config-NNNNNN/
  reference.json
  evaluation-schema.json
  datasets-lock.json
```

通常workflowでは `config/current.json` の `config_version` を読みます。

```json
{
  "schema_version": 1,
  "config_version": "config-000002"
}
```

過去runを再現する場合は環境変数で明示できます。

```text
HF_CONFIG_VERSION=config-000002
```

`hf-fetch-revisions.sh` は選択されたversionを `.ci/hf/config/resolved.json` に保存し、`run-context.json.revisions.config_version`にも伝播させます。

## Validate HF Layout

PR/push時はRepository内のcontractだけを検証し、mutableな実Bucket状態には依存しません。

```text
pull_request / push
  -> local-contracts
  -> source-controlled config/schema/scripts
  -> synthetic revision fixtures
  -> ID allocator unit tests
```

手動実行時だけ実Bucketをstrictに確認します。

```text
workflow_dispatch
  -> hf_bucket解決
  -> config/current.json取得
  -> config/versions/<config_version>/取得
  -> strict RevisionBundle validation
  -> target identity validation
  -> required Bucket layout validation
```

required collectionsには次を含みます。

```text
benchmarks
runs
candidates
experiments
reference
scripts
tmp
```

## 自動採番

`candidate_id` と `experiment_id` の新規発行は人間が番号を決めません。

```text
<prefix>-NNNNNN
```

数値suffixはcollection全体の既存最大値+1です。prefix別カウンタではありません。

例:

```text
experiments/
  cpu-full-eval-000002
  graph-optimization-000003
  rust-eval-000007
```

次に`cpu-full-eval`を発行しても `cpu-full-eval-000008` です。

採番直後に `README.md` を作成してパスをmaterializeし、prefix・sequence・target・candidate・GitHub run等を記録します。

### concurrency

`list -> max + 1` のraceを避けるため、採番jobのみBucket単位で直列化します。

```yaml
concurrency:
  group: hf-experiment-id-${{ inputs.hf_bucket }}
  cancel-in-progress: false
```

重いmatrix evaluationは採番終了後に並列実行されます。

## candidate_id入力の意味

評価workflowの `candidate_id` は残しますが、これは採番ではありません。

```text
新しいcandidateを作る
  -> hf-push-candidate.sh が自動採番

既存candidateを評価する
  -> workflow input candidate_id で対象を明示
```

評価時に「最新candidate」を暗黙選択するとrerunの対象が変わるため、既存artifact選択は明示的に維持します。

## CPU Full Evaluation

入力:

```text
hf_bucket
candidate_id
```

内部フロー:

```text
allocate-experiment
  -> cpu-full-eval-NNNNNN
  -> README reservation

Linux CPU evaluation
  -> current config version取得
  -> strict revision validation
  -> candidate取得
  -> evaluation
  -> run-context.metadata.experiment_id
  -> runs / benchmarks
```

## Cross Platform ONNX Parity

入力:

```text
hf_bucket
candidate_id
evaluation = smoke | parity | coreml-parity
```

1回のworkflow全体に、例えば次を1つ発行します。

```text
cross-platform-parity-000023
```

Linux CPU / Windows CPU / macOS CPU / macOS CoreML matrixは同じexperiment IDを共有し、それぞれ独立したrun IDを持ちます。

## Rust Cross Platform Evaluation

入力:

```text
hf_bucket
candidate_id
evaluation = smoke | parity | coreml-parity | full
```

1回のworkflowに次のようなexperiment IDを発行します。

```text
rust-eval-000024
```

Rust evaluatorも `config_version` とstrict revision identityをrun-contextへ記録し、`--experiment-id`でexperimentを関連付けます。

## reference.json

全targetで以下を独立して固定します。

```text
development_artifact
upstream
tokenizer
reference
decoders
```

Bucket名は`reference.json`には記録せず、routingは`HF_TARGETS_JSON`のみで管理します。

## Rust CI / Release

`rust-ci.yml` はHF targetを必要とせず、Linux CPU / Windows DirectML / macOS CoreML featureをcompile/testします。

`rust-release.yml` もHF storageから独立し、GitHub Release用binaryを生成します。

## 関連文書

```text
docs/hf-bucket-operations.md  # 他repoにも移植可能な完全運用仕様
docs/hf-layout.md             # このrepoのcanonical tree
docs/multi-framework-asr.md   # ASR target/revision contract
```
