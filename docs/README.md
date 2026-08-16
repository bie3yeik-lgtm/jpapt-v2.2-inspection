# ドキュメント一覧

本ディレクトリの文書は、NeMo/Transformersを別々の運用体系として説明せず、共通ASR開発基盤を先に定義し、framework固有差分を必要な文書だけで説明する方針で統一しています。

## 最初に読む文書

1. [`architecture.md`](./architecture.md) — Repository全体の責務と共通ライフサイクル
2. [`multi-framework-asr.md`](./multi-framework-asr.md) — NeMo/Transformers、CTC/TDT/Whisperの差分
3. [`development.md`](./development.md) — ローカル開発と実装フロー
4. [`evaluation.md`](./evaluation.md) — 品質評価・parity・run contract

## Hugging Face運用

- [`hf-layout.md`](./hf-layout.md) — Bucketのcanonical tree
- [`hf-bucket-operations.md`](./hf-bucket-operations.md) — 他Repositoryにも移植可能なBucket運用仕様
- [`hf-routing-snapshots.md`](./hf-routing-snapshots.md) — `HF_TARGETS_JSON`の現在routingと過去run再現
- [`github-actions.md`](./github-actions.md) — GitHub Actionsからのtarget/config/candidate/experiment運用

## Runtime / Export

- [`onnx-export.md`](./onnx-export.md) — framework別export差分とcandidate生成
- [`execution-providers.md`](./execution-providers.md) — CPU/CUDA/DirectML/CoreML
- [`rust-first.md`](./rust-first.md) — Rust runtime/evaluatorの責務と現在の対応範囲

## 共通用語

```text
Target
  論理的なmodel開発対象。model/framework/decoder/storage routingを解決する単位。

Config Version
  config-NNNNNN。reference/evaluation/dataset revisionのimmutableな集合。

Candidate
  正式評価対象としてBucketへ保存されたdeployment artifact。

Experiment
  複数runを束ねる論理的な試行・評価単位。

Run
  1環境・1providerで行われた具体的なexecution。

Reference
  canonical expected resultを生成するframework implementation。

Upstream
  ONNX変換元・reference元となる原model snapshot。

Development Artifact
  自分たちが生成・promotionするHF Model Repo側artifact snapshot。
```

## 現在の重要な実装制約

共通contract、HF storage、revision validationはNeMo/Transformers両方を表現できます。一方、現在のPython/Rust ONNX evaluatorはCTC中心です。

```text
Parakeet CTC                    現在の主要評価runtime
Parakeet TDT                    runtime未完成
Transformers / Whisper reference 対応
Whisper autoregressive ONNX評価  未完成
```

この実装差を、Bucket構造やconfig schemaの差として扱わないことが本ドキュメント体系の基本方針です。