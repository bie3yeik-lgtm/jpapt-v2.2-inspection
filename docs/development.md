# 開発ガイド

## 基本方針

本リポジトリはNeMo専用でもTransformers専用でもありません。開発時はまずtargetを選び、そのtargetが要求するcanonical framework、decoder、export/runtime adapterを使います。

```text
Target選択
  ↓
config version取得
  ↓
reference / export / evaluation
```

## 対応環境

```text
Linux / WSL2
Windows
macOS Apple Silicon
```

| 環境 | 主な用途 |
|---|---|
| Linux / WSL2 | canonical reference、Docker、CPU、CUDA、export |
| Windows | ONNX Runtime CPU/CUDA/DirectML、Rust native |
| macOS Apple Silicon | ONNX Runtime CPU/CoreML EP、Apple Silicon検証 |

macOSではMLXを主runtimeとして使用せず、ONNX Runtime CoreML EPを使います。

## セットアップ

Unix系:

```bash
scripts/dev/setup.sh
```

Windows:

```powershell
scripts/dev/setup.ps1
```

Pythonはuv/mise管理環境を使います。

```bash
mise exec -- uv run python scripts/dev/doctor.py
```

## 開発対象の選び方

modelの意味:

```text
config/models/
```

HF targetの意味:

```text
config/hf-targets/
```

Evaluator実装能力:

```text
config/evaluators/
```

GitHub Actionsのstorage routingは`HF_TARGETS_JSON`から解決します。

Targetはmodel/framework/decoderの論理対象であり、現在のBucket名そのものをidentityにはしません。

## Revision config取得

```text
config/current.json
  ↓
config/versions/config-NNNNNN/
```

通常:

```bash
bash scripts/hf/hf-fetch-revisions.sh
```

過去version:

```bash
HF_CONFIG_VERSION=config-000023 \
  bash scripts/hf/hf-fetch-revisions.sh
```

ローカル展開:

```text
.ci/hf/config/
  resolved.json
  revisions/
    reference.json
    evaluation-schema.json
    datasets-lock.json
```

## 新しいConfig Versionをpublishする

```bash
bash scripts/hf/hf-push-config-version.sh <local-config-dir>
```

このscriptは3 JSONを検証した後、中央Allocatorから次の`config-NNNNNN`を取得します。番号を手入力しません。

```text
strict validation
  ↓
central allocator reservation
  ↓
revision JSON upload
  ↓
config/current.json update
```

他Repositoryから利用する場合は中央Allocator Repositoryへアクセス可能な`HF_ALLOCATOR_GITHUB_TOKEN`が必要です。

## DatasetとAudio

全targetでdataset解決とaudio materializationは共通です。

```text
manifest + datasets-lock
  ↓
DatasetResolver
  ↓
DatasetMaterializer
  ↓
ResolvedDatasetSample.audio_path
  ↓
CanonicalAudio(float32/mono/16kHz)
```

model-specific frontendはCanonicalAudio以降です。

## Canonical reference

Reference実装はtargetに応じて変わります。

```text
NeMo target          -> NeMo adapter
Transformers target  -> Transformers adapter
```

`reference.json`で固定されたupstream/tokenizer/reference revisionを使います。

## Export

export結果はまずローカル一時領域へ作成します。

```text
tmp/export/<work-dir>/
```

この段階では正式candidate IDは不要です。

```text
candidate_id = unallocated
```

正式publish:

```bash
bash scripts/hf/hf-push-candidate.sh ./tmp/export/work [prefix]
```

内部:

```text
central allocatorへcandidate ID要求
  ↓
Bucket上README予約
  ↓
metadata.jsonへcandidate_id反映
  ↓
artifact upload
```

## 中央Allocatorを直接利用する

通常はpublish/evaluation scriptから自動利用されます。必要な場合の公開clientは:

```bash
HF_BUCKET=owner/bucket \
  bash scripts/hf/hf-request-id.sh experiments my-experiment
```

`hf-allocate-id.sh`を直接呼んでも、中央workflow外ではこのclientへ転送されます。

複数Repositoryで同じBucketを利用するときも、各Repoで独自に`max+1`を計算してはいけません。

詳細: [`central-allocator.md`](./central-allocator.md)

## BucketルートREADME

中央Allocatorが番号を予約するたびにBucketルートREADMEのmanaged blockが更新されます。

```text
candidates 現在番号
experiments 現在番号
config 現在番号
直近の採番
```

ここに表示される番号は「予約済み最大値」です。後続publish失敗時も再利用しません。

## Evaluation

既存candidateを評価するときだけ`candidate_id`を明示します。これは採番ではなく再現性のためのartifact selectionです。

```bash
bash scripts/hf/hf-fetch-candidate.sh <candidate-id>
```

Python evaluator概念例:

```bash
python -m parakeet_onnx.cli.evaluate \
  --model-config <target-id> \
  --candidate-id <candidate-id> \
  --provider cpu \
  --evaluation smoke \
  --output results/run
```

## Evaluator capability

workflowや運用scriptで`decoder == ctc`のような分岐を増やしません。

```bash
python scripts/ci/validate-evaluator-capability.py \
  --evaluator python-onnx \
  --decoder <resolved-decoder>
```

現在の宣言:

```text
python-onnx -> ctc
rust-onnx   -> ctc
```

Whisper autoregressiveやTDTを実装した後は、runtime adapterと`config/evaluators/*.toml`を拡張します。

## ExperimentとRun

評価workflow開始時にexperiment IDを中央Allocatorが発行します。

```text
cpu-full-eval-NNNNNN
cross-platform-parity-NNNNNN
rust-eval-NNNNNN
```

1 experimentは複数runをまとめられます。cross-platform matrixでは全jobが同じexperiment IDを共有し、各実行は別run IDを持ちます。

## Rust開発

RustはHF datasetsやframework loaderを全面移植せず、Python側で解決済みのmanifest/configを受け取ってruntime/evaluationを実行します。

```text
Python preparation
  ↓
resolved manifest / revision bundle / candidate
  ↓
Rust runtime + decoder + metrics
```

Rust runtimeが対応するdecoderは`config/evaluators/rust-onnx.toml`で宣言します。

## キャッシュと生成物

Gitへcommitしない代表例:

```text
.cache/
.ci/
results/
tmp/
target/
.venv/
*.onnx
*.nemo
*.wav
*.npy
*.npz
```

## 推奨作業順

```text
1. target/config versionを固定
2. dataset/audioを解決
3. canonical referenceを生成
4. export
5. central allocator経由でcandidateをpublish
6. evaluator capabilityを確認
7. smoke/parity/full評価
8. provider差分を確認
9. acceptance確認
10. Model Repoへpromotion
```

関連文書:

```text
docs/multi-framework-asr.md
docs/onnx-export.md
docs/central-allocator.md
docs/github-actions.md
```
