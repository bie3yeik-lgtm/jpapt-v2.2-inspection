# GitHub Actions 利用ガイド

本リポジトリのHF連携workflowは、Repository Variable `HF_TARGETS_JSON` を基準にASR targetを解決します。

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

GitHub ActionsはRepository Variableから`workflow_dispatch`のchoice一覧を動的生成できません。そのため`hf_bucket`は文字列入力です。ただし入力値は実行開始直後に`HF_TARGETS_JSON`と照合され、不明なBucketは拒否されます。

内部では次の順で解決します。

```text
hf_bucket
  -> vars.HF_TARGETS_JSON
  -> target id
  -> HF_MODEL_REPO
  -> canonical framework
  -> decoder
  -> target固有 model config
```

revision policyやlegacy modeはありません。すべてのtargetが同じstrict revision contractを使用します。

## Validate HF Layout

PR/push時はRepository内のcontractだけを検証します。実HF Bucketのrevision metadataは読みません。

```text
pull_request / push
  -> local-contracts
  -> source-controlled config/schema/scriptsを検証
  -> synthetic fixtureでstrict revision loaderをテスト
  -> config/hf-targets/*.tomlを検証
```

実HF Bucketを検証するのは手動実行時だけです。

```text
workflow_dispatch
  -> local-contracts
  -> validate-selected
  -> hf_bucketを解決
  -> remote revision filesを取得
  -> strict RevisionBundle validation
  -> target identity validation
  -> Bucket directory validation
```

手動実行:

```text
Actions
  -> Validate HF Layout
  -> Run workflow
  -> hf_bucket
```

Bucket側の`reference.json`がまだ新contractへ移行されていない期間は、PR/push CIには影響しません。移行後に手動`Validate HF Layout`を実行して実値を検証します。

## Revision fetch/validation

`hf-fetch-revisions.sh` は次の3ファイルを取得します。

```text
config/revisions/reference.json
config/revisions/evaluation-schema.json
config/revisions/datasets-lock.json
```

取得後は必ずproject `RevisionBundle` loaderを実行します。`uv`があれば`uv run python`、なければactive `python`を使用しますが、validation自体をskipする経路はありません。

その後 `validate-revisions.py` が選択targetとのidentityを照合します。

```text
development_artifact.repo_id
upstream.repo_id
tokenizer.repo_id
reference.canonical_framework
decoders
```

## reference.json

全targetで以下の3 identityが必須です。

```json
{
  "schema_version": 1,
  "development_artifact": {
    "repo_id": "gawohok7/tf-v1-onnx-dev",
    "revision": "<artifact-sha>"
  },
  "upstream": {
    "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
    "revision": "<upstream-sha>"
  },
  "tokenizer": {
    "repo_id": "kotoba-tech/kotoba-whisper-v1.0",
    "revision": "<tokenizer-sha>"
  },
  "reference": {
    "id": "transformers-reference-v1",
    "revision": "<reference-revision>",
    "canonical_framework": "transformers"
  },
  "decoders": {
    "supported": ["whisper_autoregressive"],
    "default": "whisper_autoregressive"
  }
}
```

旧`model`形式、`model_id`/`model_revision`、`decorders`、単数`decoder`、旧形式と新形式の混在は受理されません。

## CPU Full Evaluation

入力:

```text
hf_bucket
candidate_id
```

処理:

```text
Bucket解決
 -> revision fetch + strict validation
 -> target identity validation
 -> decoder compatibility check
 -> candidate取得
 -> reference取得
 -> target固有 model config で Linux CPU full evaluation
 -> run/benchmark upload
```

同じ`candidate_id`でもBucketが異なる評価を互いに衝突させないよう、concurrency keyには`hf_bucket`も含めます。

現在のPython ONNX evaluatorはCTC-only実装です。`whisper_autoregressive`等の非CTC targetを選択した場合、revision検証後に明示的なdecoder compatibility errorで停止します。

## Cross Platform ONNX Parity

入力:

```text
hf_bucket
candidate_id
evaluation = smoke | parity | coreml-parity
```

matrix:

```text
Linux CPU
Windows CPU
macOS CPU
macOS CoreML
```

解決した`HF_TARGET_ID`を`--model-config`としてPython evaluatorへ渡します。concurrency keyにも`hf_bucket`を含めるため、target間でrunが誤ってcancelされません。

## Rust Cross Platform Evaluation

入力:

```text
hf_bucket
candidate_id
evaluation = smoke | parity | coreml-parity | full
```

matrix:

```text
Linux CPU
Windows CPU
macOS CPU
macOS CoreML
```

`prepare-rust-manifest.py`にも解決済み`HF_TARGET_ID`を`--model-config`として渡します。Rust evaluatorは現在CTC-onlyなので、非CTC targetはrevision検証後に明示的に停止します。

## Rust CI / Release

`rust-ci.yml` はHF target選択を必要としません。Linux CPU / Windows DirectML / macOS CoreML featureのcompile/testを行います。

`rust-release.yml` もHF storageを参照せず、`v*` tagまたは手動tag入力からLinux/Windows/macOS向け`asr-eval` binaryと`SHA256SUMS`をGitHub Releaseへ公開します。

詳細なrevision contractは `docs/multi-framework-asr.md` を参照してください。
