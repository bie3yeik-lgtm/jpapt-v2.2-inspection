# Workflows

## GitHub ActionsとHF Jobsの責務

NeMo/PyTorch依存の重い処理をGitHub Actionsへ混ぜず、source framework処理はHF Jobs、repository contract/runtime acceptanceはGitHub Actions + Rustへ分離する。

```text
HF Jobs
  ├─ exact .nemo load
  ├─ NeMo→ONNX export
  ├─ frontend/reference fixture
  ├─ NeMo reference transcript
  └─ validation bundle upload

GitHub Actions
  ├─ repository/static contract validation
  ├─ Rust build/test
  ├─ Bucket bundle fetch
  └─ release asr-eval validation
```

## NeMo ONNX validation workflow

`.github/workflows/nemo-onnx-validation.yml`はmanual dispatch専用である。

主要入力:

```text
bucket_id
bundle_prefix
require = ctc | tdt
confirmation
```

`confirmation`は次と完全一致する。

```text
<bucket_id>:<bundle_prefix>:<require>
```

workflowはbundleを修復しない。remote evidenceを取得し、Release Rust CLIをbuildして次を実行する。

```bash
asr-eval nemo-onnx-validate \
  --report <bundle>/nemo-onnx-validation.json \
  --bundle-root <bundle> \
  --require ctc
```

## NeMo reference generation

HF Jobs/NeMo container内ではPython package entrypointを使う。

```bash
parakeet-nemo-reference \
  --model-revision <revision> \
  --resolved-manifest <manifest> \
  --output <bundle>/nemo-reference-quality.json
```

`scripts/hf/nemo-reference-quality.py`は互換ロジックを持たない薄いshimであり、実装正本は`python/src/parakeet_onnx/nemo/`である。

## Quality workflowの組み立て

品質測定には以下が同じ実行環境でmaterializeされている必要がある。

- generated candidate contract
- candidate artifacts
- run context
- resolved manifest
- resolved manifestが指すaudio files
- NeMo reference evidence
- NeMo→ONNX validation bundle

その状態でRelease Rust CLIを実行する。

```bash
asr-eval nemo-onnx-quality \
  --provider cpu \
  --candidate-contract ... \
  --run-context ... \
  --resolved-manifest ... \
  --nemo-reference ... \
  --nemo-validation-report ... \
  --nemo-validation-bundle-root ... \
  --output ... \
  --max-cer-regression ... \
  --max-wer-regression ...
```

音声datasetをGitHub Actions側で推測して再取得するworkflowにはしない。resolved manifest/materialization contractを正本とする。

## Bucket initialization

`.github/workflows/hf-bucket-init.yml`は新規Bucket初期化専用。詳細は[hf-bucket-initialization.md](hf-bucket-initialization.md)を参照。

## CI

通常PRでは最低限以下を通す。

```text
Validate HF Layout
Python Unit
Rust CI
  ├─ rustfmt
  ├─ Linux CPU
  ├─ Windows DirectML
  └─ macOS CoreML
```

Pythonのunit testではNeMo本体をimportしない。NeMo reference contract、normalization、schema registry、manifest/audio identityなどを純Pythonで検証する。実NeMo load/transcribeはHF Jobsで行う。

## 一時workflow

formatter/bootstrap用の一時workflowをbranchへ残さない。必要な場合でもone-shot実行後に削除し、最終treeには通常運用workflowだけを残す。

## HF Jobs connector制約

connector/API層でjob owner metadataのdeserializeに失敗する場合、job submit成功を推測して品質値を報告しない。job ID/log/resultが取得できない場合は「実測未確認」とする。

同じ理由で、job count増加だけをASR成功の証拠にしない。
