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

### `HF_TARGETS_JSON` は現在routingのsnapshot

`HF_TARGETS_JSON` は恒久的な target→Bucket identity ではなく、**現在どのtargetをどのBucketへrouteするか**を表す運用snapshotです。

同一snapshot内では `HF_BUCKET` は必ず一意です。したがって現在の値だけを見れば、`hf_bucket` からtargetを一意に逆引きできます。

一方で、容量・用途・運用変更により、後日のsnapshotでは同じtargetの `HF_BUCKET` を別Bucketへ変更して構いません。過去に別targetが利用していたBucketを後から再利用することも、現在snapshot内で重複しない限り許容されます。

```text
2026-08 snapshot
model-a -> bucket-a
model-b -> bucket-b

2026-10 snapshot
model-a -> bucket-c
model-b -> bucket-a
```

このため、過去runの再現に「現在の `HF_TARGETS_JSON`」を使って過去Bucketを推測してはいけません。Python/Rust evaluatorは実行時点のroutingを次にsnapshot保存します。

```text
run-context.json.metadata.hf_target_id
run-context.json.metadata.hf_bucket
run-context.json.metadata.hf_model_repo
```

`HF_TARGETS_JSON` は現在routing、`run-context.json` は過去実行時routingの記録、という責務分離です。

## HF Bucketを選択するworkflow

次の手動workflowは共通して `hf_bucket` を入力に持ちます。

```text
Validate HF Layout
CPU Full Evaluation
Cross Platform ONNX Parity
Rust Cross Platform Evaluation
```

GitHub ActionsはRepository Variableから`workflow_dispatch`のchoice一覧を動的生成できないため、`hf_bucket`は文字列入力です。実行時にその時点の`HF_TARGETS_JSON`と照合し、不明なBucketまたは同一snapshot内の重複Bucketを拒否します。

```text
hf_bucket
  -> current vars.HF_TARGETS_JSON
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

過去runを再現する場合は、まず `run-context.json.metadata.hf_bucket` で当時のBucketを特定し、そのうえで `run-context.json.revisions.config_version` を使用します。

```text
HF_BUCKET=<run時点のBucket>
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
  -> current HF_TARGETS_JSONからhf_bucket解決
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

採番直後に `README.md` を作成してパスをmaterializeし、prefix・sequence・**採番時点のtarget/Bucket routing**・candidate・GitHub run等を記録します。このREADMEのtarget/Bucket対応も恒久mappingではなくallocation-time snapshotです。

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
  -> current HF_TARGETS_JSONの一意性確認
  -> cpu-full-eval-NNNNNN
  -> README reservation

Linux CPU evaluation
  -> current config version取得
  -> strict revision validation
  -> candidate取得
  -> evaluation
  -> run-context.metadata.experiment_id
  -> run-context.metadata.hf_bucket / hf_target_id / hf_model_repo
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

Linux CPU / Windows CPU / macOS CPU / macOS CoreML matrixは同じexperiment IDを共有し、それぞれ独立したrun IDとexecution-time routing snapshotを持ちます。

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

Rust evaluatorも `config_version`、strict revision identity、実行時点のHF routing snapshotをrun-contextへ記録し、`--experiment-id`でexperimentを関連付けます。

## reference.json

全targetで以下を独立して固定します。

```text
development_artifact
upstream
tokenizer
reference
decoders
```

Bucket名は`reference.json`には記録しません。Bucketはmutableなrouting先であり、model provenance identityではないためです。

## 過去runの再現

過去runについては次の順で復元します。

```text
run-context.json.metadata.hf_bucket
  -> 当時のBucket

run-context.json.revisions.config_version
  -> 当時のimmutable config set

run-context.json.artifact.candidate_id
  -> 当時のcandidate
```

現在の `HF_TARGETS_JSON` が当時と異なっていても、この3情報から過去実行を特定できます。

## Rust CI / Release

`rust-ci.yml` はHF targetを必要とせず、Linux CPU / Windows DirectML / macOS CoreML featureをcompile/testします。

`rust-release.yml` もHF storageから独立し、GitHub Release用binaryを生成します。

## 関連文書

```text
docs/hf-bucket-operations.md  # 他repoにも移植可能な完全運用仕様
docs/hf-layout.md             # このrepoのcanonical tree
docs/multi-framework-asr.md   # ASR target/revision contract
```
