# ドキュメント一覧

本ディレクトリは、NeMoとTransformersを別々の運用体系として説明せず、共通ASR開発基盤を先に定義し、framework・runtime profile・Execution Provider固有差分だけを必要な文書へ閉じ込める方針で統一しています。

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

## 共通ライフサイクル

```text
Target
  ↓ profile_set
ASR Catalog
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

NeMo/TransformersやCTC/TDT/Whisper autoregressiveの違いはBucket treeの違いではありません。中央ASR catalogのruntime profileとreference/runtime adapterの違いとして扱います。

---

## 共通用語

### ASR Catalog

```text
config/asr-catalog.json
```

再利用可能な、

```text
ID prefix
decoder profile
artifact contract
required artifact roles
tokenizer kind
required runtime features
profile set / runtime variant
```

を集約するSource of Truthです。

### Runtime Profile

例えば、

```text
ctc-v1
tdt-v1
whisper-autoregressive-v1
```

です。

candidate固有のtensor bindingではなく、「そのruntimeが何を要求するか」を表します。

### Profile Set

1 target/candidateが利用できるruntime profileの集合です。

例:

```text
parakeet-tdt-ctc-v1
    ctc -> ctc-v1
    tdt -> tdt-v1
```

CTC/TDTを切り替えてもJSONを書き換えません。

### Runtime Variant

profile set内で実際に選択するkeyです。

```text
ctc
tdt
whisper
```

CLI/Actionsで選択し、run-contextへsnapshotします。

### Target

論理的なmodel開発対象です。

```text
model
upstream
canonical framework
runtime profile set
```

を表します。

storage routingそのものはTarget identityではなく、実行時に`HF_TARGETS_JSON`から解決します。

### Config Version

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

### Candidate

正式評価対象としてBucketへ保存されたdeployment artifact bundleです。

schema-v3では同一candidateにCTC/TDT等の複数variantを保持できます。

### Experiment / Run

```text
Experiment
    複数runを束ねる論理的な試行単位

Run
    1環境・1provider・1runtime variantの具体的execution
```

---

## JSON/TOML正規化

同じ意味を複数ファイルへコピーしません。

```text
Reusable policy / semantics
    config/asr-catalog.json

Model provenance
    reference.json

Evaluation policy
    evaluation-schema.json

Dataset provenance
    datasets-lock.json

Config -> runtime family relation
    runtime.json

Artifact-specific facts
    candidate metadata.json

Actual execution snapshot
    run-context.json
```

詳細は [`json-contract-design.md`](./json-contract-design.md) を参照してください。

---

## Storage routingと履歴

`HF_TARGETS_JSON` は現在時点のrouting snapshotです。同一snapshot内では `HF_BUCKET` は一意ですが、targetとBucketの対応は将来変更できます。

```text
現在のrouting      HF_TARGETS_JSON
実行時routing      run-context.json.metadata
model provenance   reference.json
runtime semantics  runtime.json + locked catalog SHA
```

過去runの再現では現在のRepository VariableからBucketを推測せず、run-contextに保存されたsnapshotを使用します。

---

## 自動採番

candidate、experiment、config versionの数値suffixは人間が決めません。

```text
Repo A ─┐
Repo B ─┼─> Central Allocator -> HF Bucket
Repo C ─┘
```

prefix文字列もWorkflowへ分散させません。

```text
experiment.cpu_full
        ↓ ASR Catalog
cpu-full-eval
        ↓ allocator
cpu-full-eval-000123
```

採番のたびにBucketルート`README.md`のmanaged blockも更新されます。

---

## Evaluator capability

workflowはCTC/TDT/Whisperを条件分岐しません。

```text
Runtime Profile requirement
        ↓
Candidate binding
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

TDT/Whisperについてはruntime抽象とsynthetic contract testは存在しますが、実candidateに対するNeMo/Transformers canonical parityは別途integration validationが必要です。

この「実装能力の差」をBucket構造やJSON schemaの差として表現しないことが、本ドキュメント体系の基本方針です。
