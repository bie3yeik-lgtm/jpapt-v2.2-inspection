# Development

## 基本方針

このrepositoryは未使用contractについて後方互換を優先しない。曖昧な旧schema/APIを互換shimで延命するより、producer/consumer/test/docsを同じcommit/PR stackで破壊的に揃える。

## Pythonの責務

Python packageは以下を担当する。

```text
config/revision resolution
dataset resolution/materialization
source framework adapters
NeMo reference evidence generation
ONNX export support
JSON Schema structural validation
diagnostic evaluator helpers
```

NeMo reference実装の正本:

```text
python/src/parakeet_onnx/nemo/
├── __init__.py
├── contracts.py
└── reference.py
```

CLI:

```text
python/src/parakeet_onnx/cli/nemo_reference.py
```

`scripts/hf/nemo-reference-quality.py`はthin shimのみである。scriptにbusiness logicを再追加しない。

## 廃止したPython CLI surface

次はquality authorityと競合するため削除する。

```text
parakeet-onnx-compare
parakeet-onnx-benchmark
```

旧`compare`はJSON全体が完全一致するかだけを判定し、ASR品質比較ではなかった。旧`benchmark`はsession creation/metadataしか測定しなかった。今後はRust `asr-eval`のruntime/quality commandを使う。

`parakeet-onnx-evaluate`はPython diagnostic/evaluator用途として残るが、release acceptanceの正本ではない。

## NeMo依存の扱い

base Python unit test環境へNeMoを必須dependencyとして入れない。

pure Python unit test対象:

- reference typed contract
- recursive null rejection
- unknown field rejection
- normalization
- sample-set digest
- schema registry
- manifest/audio identity helpers

実NeMo import/load/transcribeはNeMo container/HF Jobsで検証する。

## Test layers

```text
Python Unit
  ├─ config/dataset contracts
  ├─ NeMo reference contract
  └─ schema registry

Rust Unit/CI
  ├─ typed validation
  ├─ artifact hash/path validation
  ├─ quality comparison logic
  └─ provider builds

HF Jobs E2E
  ├─ real .nemo load
  ├─ real export
  ├─ real transcript
  └─ real evidence bundle
```

1層の成功を他層の成功として報告しない。

## Formatting

Python:

```bash
ruff check python/src python/tests scripts
```

Rust:

```bash
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets
cargo test --locked --workspace
```

CI matrixのfeature指定はrepository workflowを正本とする。

## Schema変更

schemaを破壊的に変更する場合は同時に確認する。

1. producer
2. Python structural/typed parser
3. Rust typed parser/validator
4. unit fixtures
5. workflow inputs/outputs
6. docs JSON examples
7. Bucketに既存artifactがある場合のmigration方針

未使用schemaならmigration layerを自動追加しない。

## No guessed values

NeMo/ONNX開発で次をモデル名から推測してcodeへ固定しない。

```text
mel bins
blank ID
xscaling
dither/normalization
tensor names
state shapes
external data names
```

Model Cardで明記された静的値とcheckpoint evidenceを区別する。

## PR運用

NeMo export、quality、Bucket、providerの変更はstack PRでもよいが、base/headを明示する。draft PRは明示指示なしにready/mergeしない。

一時bootstrap workflowは最終成果物から削除する。
