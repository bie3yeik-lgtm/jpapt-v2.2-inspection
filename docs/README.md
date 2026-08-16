# ドキュメント一覧

本ディレクトリはNeMoとTransformersを別々の運用体系として説明せず、共通ASR開発基盤を先に定義し、framework・runtime profile・Execution Provider固有差分だけを必要な文書へ閉じ込める方針で統一しています。

## 最初に読む文書

1. [`architecture.md`](./architecture.md) — Repository全体の責務と共通ライフサイクル
2. [`json-contract-design.md`](./json-contract-design.md) — JSON/TOMLをどこまで中央化し、何を個別に固定するか
3. [`multi-framework-asr.md`](./multi-framework-asr.md) — NeMo/Transformers、CTC/TDT/Whisperの差分
4. [`development.md`](./development.md) — ローカル開発、config、candidate、評価の流れ
5. [`evaluation.md`](./evaluation.md) — ASR品質、parity、run contract

## Hugging Face運用

- [`hf-layout.md`](./hf-layout.md) — Bucketのcanonical tree
- [`central-allocator.md`](./central-allocator.md) — 複数Repository共通のcandidate/experiment/config自動採番
- [`candidate-metadata.md`](./candidate-metadata.md) — schema-v3 candidateとruntime variant
- [`hf-bucket-operations.md`](./hf-bucket-operations.md) — 他Repositoryにも移植可能なBucket運用全体仕様
- [`hf-routing-snapshots.md`](./hf-routing-snapshots.md) — `HF_TARGETS_JSON`の現在routingと過去run再現
- [`github-actions.md`](./github-actions.md) — GitHub Actionsからのtarget/config/candidate/experiment運用
- [`github-actions-version-policy.md`](./github-actions-version-policy.md) — Action versionを巻き戻さないための固定規則

## Runtime / Export

- [`onnx-export.md`](./onnx-export.md) — framework別export差分とcandidate生成
- [`execution-providers.md`](./execution-providers.md) — CPU/CUDA/DirectML/CoreML
- [`rust-first.md`](./rust-first.md) — Rust runtime/evaluatorの責務と現在の対応範囲

---

# 共通ライフサイクル

```text
Target
  ↓ profile_set
ASR Runtime Catalog
  ↓ runtime_variant
Runtime Profile
  ↓
Config Version
  ↓
Canonical Reference
  ↓
Export / Build
  ↓
Candidate variants
  ↓
Experiment
  ↓
Run
  ↓
Benchmark / Acceptance
  ↓
Promotion
```

NeMo/TransformersやCTC/TDT/Whisper autoregressiveの違いはBucket treeの違いではありません。runtime profileとreference/runtime adapterの違いとして扱います。

---

# 2つの中央catalog

## ASR Runtime Catalog

```text
config/asr-catalog.json
```

再利用可能なruntime semanticsを管理します。

```text
decoder profile
artifact contract
required/optional artifact roles
tokenizer kind
runtime feature requirements
profile set / variant mapping
default variant
```

## HF Allocation Catalog

```text
config/hf-allocation-catalog.json
```

採番表示名だけを管理します。

```text
candidate prefix
experiment prefix
config prefix
```

この2つを分離することで、`cpu-full-eval`等の命名変更だけでASR runtime catalog SHAが変化することを防ぎます。

---

# 共通用語

## Runtime Profile

```text
ctc-v1
tdt-v1
whisper-autoregressive-v1
```

candidate固有tensor bindingではなく、そのruntimeが要求する共通contractです。

## Profile Set

1 target/candidateが利用できるruntime profile集合です。

```text
parakeet-tdt-ctc-v1
    ctc -> ctc-v1
    tdt -> tdt-v1
```

CTC/TDTを切り替えるためにJSONを書き換えません。

## Runtime Variant

profile set内で実際に選択するkeyです。

```text
ctc
tdt
whisper
```

CLI/Actionsで選択し、run-contextへsnapshotします。

## Target

論理的なmodel開発対象です。

```text
model
upstream
canonical framework
runtime profile set
```

storage routingはTarget identityではなく、実行時に`HF_TARGETS_JSON`から解決します。

## Config Version

```text
config-NNNNNN
```

次のimmutable集合です。

```text
reference.json
evaluation-schema.json
datasets-lock.json
runtime.json
```

## Candidate

正式評価対象のdeployment artifact bundleです。schema-v3では同一candidateにCTC/TDT等の複数variantを保持できます。

## Experiment / Run

```text
Experiment  複数runを束ねる論理的な試行単位
Run         1環境・1provider・1runtime variantの具体的execution
```

---

# JSON/TOML正規化

```text
Allocation naming policy
    config/hf-allocation-catalog.json

Reusable runtime semantics
    config/asr-catalog.json

Model provenance
    reference.json

Evaluation policy
    evaluation-schema.json

Dataset provenance
    datasets-lock.json

Immutable runtime family lock
    runtime.json

Artifact-specific facts
    candidate metadata.json

Actual execution snapshot
    run-context.json
```

詳細は [`json-contract-design.md`](./json-contract-design.md) を参照してください。

---

# CTC/TDT切替

Parakeetのconfig/candidateを書き換えません。

```text
ASR_RUNTIME_VARIANT=ctc
```

または、

```text
ASR_RUNTIME_VARIANT=tdt
```

を選択します。

```text
Target profile_set
    ↓
ASR runtime catalog
    ↓ variant
resolved runtime profile
    ↓
Candidate variants.<variant>
```

---

# Storage routingと履歴

`HF_TARGETS_JSON`は現在routing snapshotです。同一snapshot内では`HF_BUCKET`は一意ですが、targetとBucketの対応は将来変更できます。

```text
現在routing          HF_TARGETS_JSON
実行時routing        run-context.json.metadata
model provenance     reference.json
runtime semantics    runtime.json + ASR runtime catalog SHA
```

過去runの再現では現在のRepository VariableからBucketを推測せず、run-contextのsnapshotを使用します。

---

# 自動採番

candidate、experiment、config versionの数値suffixは人間が決めません。

```text
Repo A ─┐
Repo B ─┼─> Central Allocator -> HF Bucket
Repo C ─┘
```

workflowはraw prefixではなくsemantic allocation keyを渡します。

```text
experiment.cpu_full
        ↓ HF Allocation Catalog
cpu-full-eval
        ↓ allocator
cpu-full-eval-000123
```

採番のたびにBucket root `README.md` のmanaged blockも更新されます。

---

# Evaluator capability

workflowはCTC/TDT/Whisper固有条件を持ちません。

```text
Runtime Profile requirements
        ↓
Candidate bindings
        ↓
Evaluator capability
        ↓
Factory / Runtime Registry
```

現在の実装範囲:

```text
Python ONNX
    CTC                     実装済み
    TDT                     generic greedy runtime/contract実装済み
    Whisper autoregressive  encoder/decoder/KV-cache runtime実装済み

Rust ONNX
    CTC                     対応
    TDT                     capability未開放
    Whisper                 capability未開放
```

TDT/Whisperはruntime抽象とsynthetic contract testを持ちますが、実candidateに対するcanonical NeMo/Transformers parityはintegration validationが必要です。

この実装能力差をBucket treeやJSON schemaの差として表現しないことが基本方針です。
