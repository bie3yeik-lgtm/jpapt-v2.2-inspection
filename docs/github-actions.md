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

例:

```text
gawohok7/jpapt-v2.2-dev-bucket
gawohok7/tf-v1-onnx-dev-bucket
```

内部では次の順で解決します。

```text
hf_bucket
  -> vars.HF_TARGETS_JSON
  -> target id
  -> HF_MODEL_REPO
  -> canonical framework
  -> decoder
  -> revision policy
  -> target固有 model config
```

## Validate HF Layout

用途:

- Bucketのrevision lock取得
- development artifact / upstream / tokenizer identityの照合
- framework/decoder contractの照合
- `benchmarks`, `runs`, `candidates`, `reference`, `scripts`, `tmp` directoryの確認

手動実行:

```text
Actions
  -> Validate HF Layout
  -> Run workflow
  -> hf_bucket
```

手動選択はstrictです。選択したBucketのrevision metadataがsource-controlled target contractと一致しない場合は失敗します。

PR/pushの自動target matrixではremote metadata driftをwarningとして報告します。これにより外部Bucketの更新不整合だけでRepositoryのコード変更全体をブロックせず、必要な場合は手動`Validate HF Layout`でstrict validationできます。

## CPU Full Evaluation

入力:

```text
hf_bucket
candidate_id
```

処理:

```text
Bucket解決
 -> revision validation
 -> decoder compatibility check
 -> candidate取得
 -> reference取得
 -> target固有 model config で Linux CPU full evaluation
 -> run/benchmark upload
```

現在のPython ONNX evaluatorは`PythonCtcEvaluator` / `OrtCtcRunner`を使用するCTC-only実装です。そのため`whisper_autoregressive`等の非CTC targetを選択した場合、Bucket/revision解決後に明示的なdecoder compatibility errorで停止します。

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

解決した`HF_TARGET_ID`を`--model-config`としてPython evaluatorへ渡します。現行runtimeはCTC-onlyのため、非CTC targetはinference開始前に明示的に停止します。

artifact名には解決後のtarget idを使用するため、Bucket文字列に含まれる`/`をartifact名へ直接持ち込みません。

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

`prepare-rust-manifest.py`にも解決済み`HF_TARGET_ID`を`--model-config`として渡すため、dataset materializationも選択targetのmodel configを使用します。

Rust evaluatorは現在CTC-onlyです。したがってKotoba Whisper Bucketのように`whisper_autoregressive`を要求するtargetも選択・revision検証までは可能ですが、inference前に明示的なdecoder compatibility errorで停止します。

## reference.json revision contract

新規strict targetでは以下を分離します。

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
  }
}
```

意味:

```text
development_artifact = ONNX/deployment artifactのrepoとrevision
upstream             = 元モデルcheckpointのrepoとrevision
tokenizer            = tokenizer/processorのrepoとrevision
```

既存Parakeet Bucketの旧`model`形式はlegacy contractとして読み取り可能です。

詳細は `docs/multi-framework-asr.md` を参照してください。

## Rust CI / Release

`rust-ci.yml` はHF target選択を必要としません。Linux CPU / Windows DirectML / macOS CoreML featureのcompile/testを行います。

`rust-release.yml` もHF storageを参照せず、`v*` tagまたは手動tag入力からLinux/Windows/macOS向け`asr-eval` binaryと`SHA256SUMS`をGitHub Releaseへ公開します。
