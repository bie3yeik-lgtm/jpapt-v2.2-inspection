# Rust-first migration

## Status

**Completed for the defined production/runtime scope.**

Rust is the canonical implementation for stable, model-independent production/runtime responsibilities. Python remains only at explicit Python-native ML/tooling, dataset acquisition, reference/parity, and compatibility-test boundaries.

The target was not zero Python files. The target was to remove business rules, deterministic bookkeeping, runtime-critical validation policy, provider policy, HF routing/allocation policy, and canonical evaluation orchestration from Python wherever those responsibilities are not inherently Python-native.

## Canonical architecture

```text
Python-native / reference boundary
  ONNX/PyTorch/Transformers/NeMo tooling
  Hugging Face datasets
  public/reference E2E
  interoperability tests
               |
               | versioned file contracts
               v
Rust canonical core
  asr-contracts
  asr-hf
  asr-audio
  asr-runtime
  asr-metrics
  asr-eval
  asr-capsule
               |
               | thin shell + official hf/gh CLI
               v
HF Bucket / Model Repo / GitHub Actions / GitHub Releases
```

## Rust-owned responsibilities

### `asr-contracts`

- JSON/schema validation
- revision bundle validation
- resolved config identity
- run-context construction/validation
- evaluator capability policy
- provider probe context/readiness classification
- action/workflow policy validation
- ASR catalog normalization/fingerprint/summary
- promotion/config publication bookkeeping validation

### `asr-hf`

- HF target routing
- Bucket reverse lookup
- runtime variant/profile/decoder resolution
- allocation collection -> prefix policy
- canonical/historical sequence scanning
- candidate location resolution
- allocation request/response bookkeeping
- candidate sync-plan validation
- root README allocator managed block

### `asr-audio`

- canonical audio decode/resample/waveform handling

### `asr-runtime`

- ONNX Runtime
- provider registration/session/runtime handling

### `asr-metrics`

- text normalization
- CER/WER
- runtime/provider telemetry aggregation

### `asr-eval`

- canonical Rust evaluation orchestration
- current decoder capability: CTC

### `asr-capsule`

- ExperimentCapsuleV1 Parquet persistence
- validation/read/summary/analytics

## Current HF policy after migration

旧設計のallocation catalog/prefix-keyは廃止済みです。

現在はcollectionから直接prefixを導出します。

```text
candidates  -> candidate
experiments -> experiment
config      -> config
```

`config/hf-allocation-catalog.json` は存在しません。allocation fingerprintやprefix keyをhuman-authored inputとして復活させないでください。

candidate read/writeも次へ統一されています。

```text
new write:
  candidates/candidate-NNNNNN/

historical read-only fallback:
  candidates/<variant>/candidate-NNNNNN/
```

HF CLI listingがcollection root付きpathを返す場合もRust resolverが正規化します。

## Minimal target policy

`config/hf-targets/<target-id>.toml` は次の最小情報だけを保持します。

```text
runtime.profile_set
storage.bucket
storage.model_repo
```

導出される値:

```text
target ID                <- filename
model/upstream/framework <- config/models/<target-id>.toml
runtime profile/decoder  <- config/asr-catalog.json
candidate ID             <- explicit input or Bucket state
allocation prefix        <- collection
```

同じidentityを複数configへ再入力しません。

## Python retention policy

Python may remain when at least one of the following is true:

1. upstream libraryがPython-only、またはsupported canonical APIがPythonである。
2. Rust behaviorを検証するreference/parity implementationである。
3. official supported CLI/libraryを捨ててcustom network/protocol implementationをRustで作る方が信頼性を下げる。
4. Python-native model tooling用のtest fixture/scaffoldingである。

Python must not own:

- stable production JSON/schema policy
- deterministic filesystem/hash policy
- canonical run-context construction for Rust operation
- evaluator capability policy
- provider readiness classification
- HF target routing
- allocation prefix/sequence policy
- candidate location migration policy
- benchmark/promotion/config publication bookkeeping policy

## Intentional Python boundaries

### `scripts/ci/resolve-candidate-artifacts.py`

`CandidateArtifacts` とPython ONNX toolingを使ってactual graph/artifactをinspectionし、versioned generated candidate execution contractを出力します。

### `scripts/ci/prepare-rust-manifest.py`

Hugging Face `datasets` acquisition/materialization boundaryです。Rust evaluatorが読めるresolved manifestへ変換します。

### Public/reference E2E

例:

```text
e2e-provider-ctc.py
e2e-ctc-onnx.py
e2e-rust-ctc.py
public-model-e2e.yml 内のrevision resolution/model preparation
```

これらはproduction runtime dependencyではなくreference/proof boundaryです。

## Shell retention policy

shellは薄いtransport/orchestration wrapperとして残します。

許可される代表責務:

- env validation
- path staging
- official `hf` / `gh` CLI invocation
- Rust CLI invocation
- CI glue

stable semantic policyをawk/sed/bashで再実装しません。

## GitHub Actionsとの関係

GitHub ActionsはRust-first architectureの上位orchestration layerです。

### 常設CI

```text
Python Unit
Rust CI
Validate HF Layout
Capsule Interop
```

### Operational/manual

```text
CPU Full Evaluation
Cross Platform ONNX Parity
Rust Cross Platform Evaluation
Provider Strict Probes
Public Model E2E
HF Central Sequence Allocator
Rust Release
```

各workflowの現在のinput/runner/secret/artifactは [github-actions.md](./github-actions.md) を参照してください。

## Compatibility strategy

Python-native preparationとRust production coreの境界はversioned fileです。

必要なpattern:

```text
Python producer -> Rust consumer
Rust producer -> Python reference consumer
golden JSON/Parquet fixture -> both readers
byte/hash equality -> deterministic serialization
tolerance comparison -> numerical/model output
```

`capsule-interop.yml` はRust producer -> Python readerの具体例です。

## Dependency policy

- Rust ORT/Arrow/Parquetのcompatibility-sensitive dependencyはCargo.lockで固定する。
- Python runtimeはuv.lockを正本とする。
- Python ORTは現在 `1.28.0` pin。
- Rust ORTは現在 `2.0.0-rc.13` pin。
- official HF CLI/libraryをnetwork/auth boundaryに使用する。
- 「Python file countを減らす」だけのためにreference/ML toolingをRustへ移植しない。
- production Rust binaryがPython runtimeをshell-out dependencyとして要求する設計に戻さない。

## Completion criteria already reached

現在のproduction/runtime scopeでは次が成立しています。

- Rust run-context builder/validatorが存在する。
- Rust evaluator capability policyが存在する。
- Rust provider readiness classificationが存在する。
- Rust HF target resolverがsource-controlled configからderived stateを生成する。
- allocation catalogを削除しcollection-derived policyへ移行済み。
- candidate canonical-write / legacy-read-only migration policyがRustにある。
- benchmark/config/promotionのstable validation/bookkeepingがRustにある。
- ExperimentCapsuleV1のcanonical producer/validatorがRustにある。
- Python残存箇所はML/tooling/dataset/reference/compatibility boundaryとして説明可能である。

今後stable model-independent policyを追加する場合は、まずRust側へ実装し、Python-native boundaryからversioned fileで接続してください。
