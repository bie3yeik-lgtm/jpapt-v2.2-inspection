# ドキュメント一覧

本ディレクトリは、NeMoとTransformersを別々の運用体系として説明せず、共通ASR開発基盤を先に定義し、framework・decoder・runtime固有差分を必要な文書だけへ閉じ込める方針で統一しています。

## 最初に読む文書

1. [`architecture.md`](./architecture.md) — Repository全体の責務と共通ライフサイクル
2. [`multi-framework-asr.md`](./multi-framework-asr.md) — NeMo/Transformers、CTC/TDT/Whisperの差分
3. [`development.md`](./development.md) — ローカル開発、config、candidate、評価の流れ
4. [`evaluation.md`](./evaluation.md) — ASR品質、parity、run contract

## Hugging Face運用

- [`hf-layout.md`](./hf-layout.md) — Bucketのcanonical tree
- [`central-allocator.md`](./central-allocator.md) — 複数Repository共通のcandidate/experiment/config自動採番
- [`hf-bucket-operations.md`](./hf-bucket-operations.md) — 他Repositoryにも移植可能なBucket運用全体仕様
- [`hf-routing-snapshots.md`](./hf-routing-snapshots.md) — `HF_TARGETS_JSON`の現在routingと過去run再現
- [`github-actions.md`](./github-actions.md) — GitHub Actionsからのtarget/config/candidate/experiment運用

## Runtime / Export

- [`onnx-export.md`](./onnx-export.md) — framework別export差分とcandidate生成
- [`execution-providers.md`](./execution-providers.md) — CPU/CUDA/DirectML/CoreML
- [`rust-first.md`](./rust-first.md) — Rust runtime/evaluatorの責務と現在の対応範囲

## 共通ライフサイクル

```text
Target
  ↓
Config Version
  ↓
Canonical Reference
  ↓
Export / Build
  ↓
Candidate
  ↓
Experiment
  ↓
Run
  ↓
Benchmark / Acceptance
  ↓
Promotion
```

NeMo/TransformersやCTC/TDT/Whisper autoregressiveの違いは、このライフサイクルそのものではなく、reference adapter・export adapter・decoder・evaluator capabilityの違いとして扱います。

## 共通用語

```text
Target
  論理的なmodel開発対象。model/framework/decoder等の安定した意味を表す。
  storage routingそのものはTarget identityではなく、実行時にHF_TARGETS_JSONから解決する。

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

Evaluator Capability
  evaluator implementationが現在実行できるdecoder等の能力宣言。
```

## Storage routingと履歴

`HF_TARGETS_JSON` は現在時点のrouting snapshotです。同一snapshot内では `HF_BUCKET` は一意ですが、targetとBucketの対応は将来変更できます。

```text
現在のrouting      HF_TARGETS_JSON
実行時routing      run-context.json.metadata
model provenance   reference.json
```

過去runの再現では現在のRepository VariableからBucketを推測せず、run-contextに保存されたsnapshotを使います。

## 自動採番

candidate、experiment、config versionの数値suffixは人間が決めません。本Repositoryの `HF Central Sequence Allocator` を唯一の採番実行点とします。

```text
Repo A ─┐
Repo B ─┼─> Central Allocator -> HF Bucket
Repo C ─┘
```

採番のたびにBucketルート `README.md` のmanaged blockも更新され、`candidates` / `experiments` / `config` の現在最大番号を確認できます。

詳細は [`central-allocator.md`](./central-allocator.md) を参照してください。

## Evaluator capability

workflowは `ctc` 等のdecoder名を直接条件分岐しません。

```text
config/evaluators/python-onnx.toml
config/evaluators/rust-onnx.toml
        ↓
scripts/ci/validate-evaluator-capability.py
        ↓
実行可能 / capability mismatch
```

新しいTDT/Whisper runtimeを実装した場合は、workflowへ条件式を追加するのではなくevaluator capabilityとruntime adapterを拡張します。

## 現在の重要な実装制約

共通contract、HF storage、revision validation、routing、採番はNeMo/Transformersの両方を表現できます。一方、現在のPython/Rust ONNX evaluator capabilityはCTCのみを宣言しています。

```text
Parakeet CTC                      現在の主要評価runtime
Parakeet TDT                      runtime未完成
Transformers / Whisper reference  対応
Whisper autoregressive ONNX評価    未完成
```

この実装差をBucket構造やrevision schemaの差として扱わないことが、本ドキュメント体系の基本方針です。
