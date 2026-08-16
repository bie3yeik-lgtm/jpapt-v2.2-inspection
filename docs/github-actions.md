# GitHub Actions

現行workflowは `.github/workflows/` が正本です。

```text
python-unit.yml
validate-hf-layout.yml
rust-ci.yml
rust-release.yml
cpu-full-eval.yml
cross-platform-parity.yml
rust-eval.yml
hf-central-allocator.yml
```

## Python Unit

PR/pushでPython/config/evaluation/scripts変更を対象にprojectをinstallし、`python/tests/unit` 全体を実行します。candidate strict inspectionやmanifest contractもここで検証します。

## Validate HF Layout

source-controlled schema/catalog/profile/target/evaluator/HF contractを検証します。selected HF configurationを使うjobは入力条件に応じて実行されます。

## Rust CI

matrixで少なくとも次を確認します。

```text
rustfmt advisory
Linux CPU
macOS CoreML
Windows DirectML
```

各platform jobはCargo checkとunit testを実行します。

## Evaluation workflows

`cpu-full-eval.yml`, `cross-platform-parity.yml`, `rust-eval.yml` はcandidate/config/revisionを解決し、実評価runを生成するworkflowです。runtime variantやevaluator capabilityを無視してartifactだけを直接実行しません。

## Central allocator

`hf-central-allocator.yml` は複数callerからのsemantic allocation requestを中央採番へ変換します。candidate/config/experiment IDをcaller側で独自採番しません。

## Secrets / Variables

HF credentialやroutingはworkflow環境から供給しますが、過去run再現の正本ではありません。実行時routingはrun-contextへsnapshotします。
