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

環境ごとの主な役割は次です。

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

Pythonはuv/mise管理環境を使い、global packageへ依存しないでください。

```bash
mise exec -- uv run python scripts/dev/doctor.py
```

## 開発対象の選び方

modelの意味は`config/models/`、HF targetの意味は`config/hf-targets/`にあります。

```text
config/models/
  parakeet-tdt_ctc-0.6b-ja.toml
  kotoba-whisper-v1.0.toml
  ...

config/hf-targets/
  parakeet-tdt_ctc-0.6b-ja.toml
  kotoba-whisper-v1.0.toml
```

GitHub Actionsのstorage routingは`HF_TARGETS_JSON`から解決します。

## Revision config取得

Bucketはversioned configを使います。

```text
config/current.json
  ↓
config/versions/config-NNNNNN/
```

通常:

```bash
bash scripts/hf/hf-fetch-revisions.sh
```

過去versionを再現:

```bash
HF_CONFIG_VERSION=config-000023 \
  bash scripts/hf/hf-fetch-revisions.sh
```

ローカルには次へ展開されます。

```text
.ci/hf/config/
  resolved.json
  revisions/
    reference.json
    evaluation-schema.json
    datasets-lock.json
```

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

model-specific frontendはCanonicalAudio以降に限定します。

## Canonical reference

Reference実装はtargetに応じて変わります。

- NeMo target: NeMo adapter
- Transformers target: Transformers adapter

重要なのはframework名ではなく、`reference.json`で固定されたupstream/tokenizer/reference revisionを使うことです。

## Export

export結果はまずローカルの一時領域へ作成します。

```text
tmp/export/<work-dir>/
```

ローカルexport時点では正式candidate IDを人間が決めません。正式IDはBucketへpublishするときに自動採番します。

```bash
bash scripts/hf/hf-push-candidate.sh ./tmp/export/work
```

採番形式:

```text
<prefix>-NNNNNN
```

数値suffixは`candidates/`全体の既存最大値+1です。

## Evaluation

既存candidateを評価するときだけ`candidate_id`を明示します。これは採番ではなく、再現性のためのartifact選択です。

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

現状のPython/Rust evaluatorはCTC中心であり、Whisper autoregressive candidateの実評価は未実装です。revision/layout/referenceの共通化とは区別してください。

## ExperimentとRun

評価workflow開始時にexperiment IDを自動発行します。

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
5. candidateを自動採番してpublish
6. smoke/parity/full評価
7. provider差分を確認
8. acceptance確認
9. Model Repoへpromotion
```

framework固有の手順は`docs/multi-framework-asr.md`と`docs/onnx-export.md`を参照してください。