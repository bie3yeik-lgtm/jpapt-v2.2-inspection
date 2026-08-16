# GitHub Actions運用

## 基本設定

必須Secret:

```text
HF_TOKEN
```

他Repositoryから中央Allocatorを利用する場合:

```text
HF_ALLOCATOR_GITHUB_TOKEN
```

Repository Variable:

```text
HF_TARGETS_JSON
```

`HF_TARGETS_JSON`は現在時点のstorage routingだけを表します。

```json
{
  "target-a": {
    "HF_BUCKET": "owner/bucket-a",
    "HF_MODEL_REPO": "owner/model-a"
  }
}
```

同一snapshot内では`HF_BUCKET`は一意です。将来の容量・用途・migrationによるrouting変更は許容します。

---

# 主要workflow

```text
Validate HF Layout
HF Central Sequence Allocator
CPU Full Evaluation
Cross Platform ONNX Parity
Rust Cross Platform Evaluation
```

---

# Target / Runtime Variant解決

`scripts/ci/resolve-hf-target.py`はtargetとruntime variantを同時に解決します。

```text
HF_TARGET_ID
HF_BUCKET
HF_MODEL_REPO
EXPECTED_DEVELOPMENT_REPO_ID
EXPECTED_UPSTREAM_REPO_ID
EXPECTED_TOKENIZER_REPO_ID
EXPECTED_FRAMEWORK
HF_PROFILE_SET
ASR_RUNTIME_VARIANT
EXPECTED_RUNTIME_PROFILE
EXPECTED_DECODER
```

解決経路:

```text
HF_TARGETS_JSON
    ↓ storage routing
HF target TOML
    ↓ runtime.profile_set
config/asr-catalog.json
    ↓ runtime_variant
runtime profile / decoder
```

CTC/TDTを選択するためにJSONを書き換えません。workflow input `runtime_variant`を変更します。空の場合はprofile setの`default_variant`です。

---

# Versioned Config

```text
config/current.json
  ↓
config/versions/config-NNNNNN/
  ├── reference.json
  ├── evaluation-schema.json
  ├── datasets-lock.json
  └── runtime.json
```

`runtime.json`はASR runtime catalog id/SHAとprofile setだけをpinします。

```json
{
  "schema_version": 1,
  "catalog": {
    "id": "asr-runtime-catalog-v1",
    "sha256": "<ASR_RUNTIME_CATALOG_SHA256>"
  },
  "profile_set": "parakeet-tdt-ctc-v1"
}
```

`reference.json`/`evaluation-schema.json`へdecoder一覧を重複記述しません。

過去version再現:

```text
HF_CONFIG_VERSION=config-000023
```

---

# Central Sequence Allocator

採番対象:

```text
candidates
experiments
config
```

prefix policyのSource of Truth:

```text
config/hf-allocation-catalog.json
```

workflow/scriptはraw prefixではなくsemantic keyを使用します。

```text
experiment.cpu_full
experiment.cross_platform_parity
experiment.rust_eval
config.version
```

中央workflowだけが、

```text
list -> max suffix + 1 -> reservation -> root README update
```

を実行します。

`allocation.json`には、

```text
allocation catalog id/SHA
prefix key
resolved prefix
allocated ID
Bucket/collection
```

をsnapshotします。

詳細は [`central-allocator.md`](./central-allocator.md) を参照してください。

---

# Candidate

新規candidateはschema-v3です。

```text
metadata.catalog
metadata.profile_set
metadata.variants
```

workflowはONNX filenameやdecoder layoutを推測しません。

```text
candidate metadata
    ↓ CandidateArtifacts
runtime variant selection
    ↓
Factory / Runtime Registry
```

`candidate_id` workflow inputは採番ではなく、既存のどのcandidateを評価するかの指定です。

新規candidate publish:

```text
hf-push-candidate.sh
    ↓ schema/catalog/全variant validation
Central Allocator
    ↓
candidate ID reservation
    ↓
Bucket upload
```

---

# Evaluator capability

workflowは`EXPECTED_DECODER == ctc`等のarchitecture固有条件を持ちません。

```text
config/evaluators/python-onnx.toml
config/evaluators/rust-onnx.toml
```

と、

```text
scripts/ci/validate-evaluator-capability.py
```

で検証します。

現在:

```text
Python ONNX
  ctc                     対応
  tdt                     対応contract/runtime実装済み
  whisper_autoregressive  対応contract/runtime実装済み

Rust ONNX
  ctc                     対応
  tdt                     capability未開放
  whisper_autoregressive  capability未開放
```

TDT/Whisperの実candidate parityは別途integration validationが必要です。

---

# CPU Full Evaluation

```text
candidate_id + runtime_variant
  ↓
experiment.cpu_fullを中央Allocatorへ要求
  ↓
target/routing/profile解決
  ↓
4-file config fetch + validation
  ↓
candidate metadata/profile/capability validation
  ↓
Python Factory / Runtime Registry
  ↓
Linux CPU full evaluation
  ↓
run + benchmark upload
```

---

# Cross Platform ONNX Parity

1 workflow runに1つのexperiment IDを発行しmatrix全体で共有します。

```text
experiment.cross_platform_parity
        ↓
cross-platform-parity-NNNNNN
```

標準matrix:

```text
Linux CPU
Windows CPU
macOS CPU
macOS CoreML
```

各jobは独立run IDを持ちます。

---

# Rust Cross Platform Evaluation

```text
experiment.rust_eval
    ↓
rust-eval-NNNNNN
```

Rust evaluatorが選択variantを処理できるかは`rust-onnx` capabilityで拒否/許可します。workflow側にCTC固有if文を置きません。

---

# Validate HF Layout

PR/pushではremote Bucketを変更せずsource-controlled contractを検証します。

```text
HF target profiles
ASR runtime catalog
HF allocation catalog
candidate schema/runtime resolver
revision normalization
sequence allocator unit tests
evaluator capability
GitHub Action version policy
shell syntax
```

workflow_dispatch時のみ実Bucketを読み、

```text
config/current.json
selected config-NNNNNN
4 JSON
required lifecycle directories
```

を検証します。

---

# GitHub Action version policy

固定値:

```text
actions/checkout@v7
actions/setup-python@v7
actions/upload-artifact@v7
actions/cache@v6
actions/cache/restore@v6   when used
actions/cache/save@v6      when used
```

`scripts/ci/validate-github-action-versions.py`が全workflowを検査します。

詳細は [`github-actions-version-policy.md`](./github-actions-version-policy.md) を参照してください。

---

# 過去run再現

現在の`HF_TARGETS_JSON`から過去runのBucket/runtimeを推測しません。

```text
run-context.metadata.hf_bucket
run-context.metadata.hf_target_id
run-context.metadata.hf_model_repo
run-context.metadata.candidate.variant/profile
run-context.revisions.config_version
run-context.revisions.runtime.catalog
```

を使用します。
