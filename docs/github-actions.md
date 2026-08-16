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

`Validate HF Layout` は処理を3つに分離しています。

```text
local-contracts
  -> source-controlled config / schema / testsを検証
  -> config/hf-targets/*.tomlからtarget matrixを生成

workflow_dispatch
  -> validate-selected
  -> 指定hf_bucketをstrictに検証

pull_request / push
  -> validate-targets
  -> source-controlled targetを自動matrixで確認
```

手動実行:

```text
Actions
  -> Validate HF Layout
  -> Run workflow
  -> hf_bucket
```

手動選択では、Bucketのrevision metadataが新contractまたはtarget identityと一致しない場合は失敗します。

PR/pushの自動matrixは外部Bucket driftをwarningとして報告します。target一覧はYAMLに固定せず `config/hf-targets/*.toml` から生成されるため、新しいsource-controlled targetを追加する際にmatrix一覧を編集する必要はありません。

## Revision fetch/validation

`hf-fetch-revisions.sh` は次の3ファイルを取得します。

```text
config/revisions/reference.json
config/revisions/evaluation-schema.json
config/revisions/datasets-lock.json
```

取得後は必ず現在のPython環境から `RevisionBundle` loaderを実行します。以前のように`uv`が存在しないためproject-level validationをskipする動作はありません。

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

旧`model`形式、`model_id`/`model_revision`、`decorders`、単数`decoder`は受理されません。Bucket側を新形式へ移行してから手動`Validate HF Layout`を実行してください。

## CPU Full Evaluation

入力:

```text
hf_bucket
candidate_id
```

処理:

```text
Bucket解決
 -> revision fetch + strict schema validation
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
