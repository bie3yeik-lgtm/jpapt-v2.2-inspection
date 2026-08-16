# GitHub Actions

この文書は `.github/workflows/` の現行YAMLを基準に、各Actionのtrigger、input、runner、secret、生成物、用途をまとめます。

## 1. Workflow一覧

| Workflow | Trigger | 主目的 |
|---|---|---|
| `python-unit.yml` | PR / `main` push | Python locked環境とunit tests |
| `rust-ci.yml` | PR / `main` push | Rust fmt/check/clippy/testを3 OS matrixで検証 |
| `validate-hf-layout.yml` | PR / `main` push / manual | source-controlled contractと選択HF target/Bucketを検証 |
| `capsule-interop.yml` | PR / `main` push | Rust生成ExperimentCapsuleV1をPython readerで検証 |
| `cpu-full-eval.yml` | manual | Linux CPUのPython full evaluation、HF run/benchmark publish |
| `cross-platform-parity.yml` | manual | Python evaluatorのLinux/Windows/macOS parity + CoreML |
| `rust-eval.yml` | manual | canonical Rust CTC evaluatorを5環境matrixで実行 |
| `provider-strict-probes.yml` | manual +限定branch push | DirectML/CoreML strict readiness proof |
| `public-model-e2e.yml` | manual +限定branch push | public model/datasetでreference E2E |
| `hf-central-allocator.yml` | manual/他workflow dispatch | candidate/experiment/configの中央採番 |
| `rust-release.yml` | `v*` tag push / manual | `asr-eval` binaryを3 platformでbuildしGitHub Releaseへ公開 |

## 2. 共通設計

GitHub Actionsはruntime semanticsのsource of truthではありません。workflowは次を呼び出すexecution/orchestration layerです。

```text
config/asr-catalog.json
config/hf-targets/*.toml
config/models/*.toml
config/providers/*.toml
config/environments/*.toml
config/evaluation/*.toml
config/evaluators/*.toml
evaluation/schemas/*.schema.json
Rust CLI (asr-contracts / asr-hf / asr-eval / asr-capsule)
Python-native ML/dataset preparation boundary
official hf / gh CLI
```

workflowへcandidate prefix、decoder mapping、artifact role、Bucket path ruleを再実装しません。

## 3. Secrets / permissions

### `HF_TOKEN`

HF Bucket、Model Repo、revision/candidate fetch、run/benchmark uploadに使用します。

利用workflow:

- `validate-hf-layout.yml` のmanual selected-target validation
- `cpu-full-eval.yml`
- `cross-platform-parity.yml`
- `rust-eval.yml`
- `hf-central-allocator.yml`

### `HF_ALLOCATOR_GITHUB_TOKEN`

評価workflowからcentral allocatorをdispatch/追跡するためのGitHub tokenです。未設定時は `${{ github.token }}` をfallbackとして使う設計です。

`GH_TOKEN` として以下に設定されます。

```text
cpu-full-eval.yml
cross-platform-parity.yml
rust-eval.yml
```

### Permissions

通常CIは原則 `contents: read`。allocatorを呼ぶ評価workflowは `actions: write` を持ちます。release workflowのみGitHub Release作成のため `contents: write` を持ちます。

## 4. `python-unit.yml`

### Trigger

PRおよび`main` pushで、次のpath変更時に起動します。

```text
.github/workflows/**
pyproject.toml
uv.lock
config/**
evaluation/**
python/**
scripts/**
```

### Runner

`ubuntu-latest`, timeout 30分。

### 実行内容

```bash
python 3.12
pip install uv
uv lock --check
uv sync --locked --extra datasets --extra onnx --extra dev
```

さらに `onnxruntime == 1.28.0` をruntimeで検証し、available providersを出力した後:

```bash
uv run python -m pytest -q python/tests/unit
```

### 意味

Python-native ML/tooling boundaryとPython compatibility layerがlocked dependency上で成立することを検証します。Rust production policyの代替ではありません。

## 5. `rust-ci.yml`

### Trigger

PR / `main` pushで以下を監視します。

```text
Cargo.toml
Cargo.lock
rust/**
.github/workflows/rust-*.yml
```

### Jobs

`rustfmt` + platform matrix。

| job | runner | feature |
|---|---|---|
| `linux-cpu` | `ubuntu-latest` | `cpu` |
| `windows-directml` | `windows-latest` | `cpu,directml` |
| `macos-coreml` | `macos-15` | `cpu,coreml` |

各matrixで:

```bash
cargo metadata --locked --no-deps --format-version 1
cargo check --locked --workspace --no-default-features --features <features>
cargo clippy --locked --workspace --all-targets --no-default-features --features <features> -- -D warnings
cargo test --locked --workspace --no-default-features --features <features>
```

`cargo fmt --all -- --check` は独立jobです。

### Cache

Cargo registry/git、ORT download cache、`target` をmatrixごとのkeyでcacheします。

### 注意

このCIはprovider featureがcompile/link/testできることを確認しますが、real modelが実acceleratorで実行された証明ではありません。strict provider proofは別workflowです。

## 6. `validate-hf-layout.yml`

### Trigger

- PR
- `main` push
- manual `workflow_dispatch`

PR/pushでは `docs/**` も監視対象なので、docs変更でもcontract validationが走ります。

manual input:

```text
hf_target        required, default parakeet-tdt_ctc-0.6b-ja
runtime_variant  optional, blank = catalog default
```

### Job 1: `Validate local HF contracts`

`ubuntu-latest`, Python 3.12 + Rust stable。

locked environment:

```bash
uv lock --check
uv sync --locked --extra datasets --extra onnx --extra hf --extra dev
```

pin checks:

```text
onnxruntime == 1.28.0
huggingface_hub == 1.24.0
```

主要validation:

```bash
python scripts/dev/verify-python-first.py
python scripts/dev/doctor.py
cargo run --locked -p asr-hf -- validate-targets
cargo run --locked -p asr-contracts --bin asr-action-policy
cargo run --locked -p asr-contracts --bin asr-catalog -- fingerprint catalog_id
cargo run --locked -p asr-contracts --bin asr-catalog -- fingerprint sha256
```

allocation prefixもRustで確認します。

```text
candidates  -> candidate
experiments -> experiment
config      -> config
```

`config/hf-allocation-catalog.json` が存在しないことも明示検証します。

HF shell syntax、revision/candidate/catalog/runtime/optimizer関連のfocused Python testsも実行します。

### Job 2: `Validate selected HF configuration`

manual dispatch時のみ実行。

1. `asr-hf resolve-target`
2. `HF_TOKEN`, Bucket, Model Repoの解決確認
3. `hf-fetch-revisions.sh`
4. 4-document revision bundle validation
5. Bucket required directories確認
6. candidate listingを `resolve-candidate-location` で解決

required Bucket dirsとして現行workflowは以下も存在確認します。

```text
benchmarks
runs
candidates
experiments
reference
scripts
tmp
```

## 7. `capsule-interop.yml`

### Trigger

PR / `main` pushでcapsule Rust/Python関連pathが変わった場合。

### Flow

1. Rust locked workspace確認
2. Python locked environment (`datasets`, `dev`) 構築
3. Rust example `write_fixture` で `target/capsule-interop/run.parquet` を生成
4. Pythonの `read_experiment_capsule` / `summarize_experiment_capsule` で読み込み
5. run ID、metric、diagnostic metadataをassert

これは **Rust producer -> Python reference consumer** のversioned file contract互換性テストです。

## 8. `hf-central-allocator.yml`

### Input

```text
request_id      required
hf_bucket       required (namespace/bucket)
collection      required: candidates | experiments | config
metadata_json   optional, default {}
```

### Concurrency

```text
hf-central-sequence-<bucket>
cancel-in-progress: false
```

同一Bucketの採番を直列化し、sequence競合を避けます。

### Flow

1. official HF CLIをinstall
2. `scripts/hf/hf-allocate-id.sh <collection>`
3. Bucket root allocator status README更新
4. Rust `write-allocation-response`
5. `allocation.json` をGitHub artifactとして1日保持

response schema v4の最小fieldは次です。

```text
schema_version
request_id
id
bucket
collection
```

prefix keyやallocation catalog fingerprintはありません。

## 9. `cpu-full-eval.yml`

manual full evaluationです。

### Inputs

```text
hf_target        required, default parakeet-tdt_ctc-0.6b-ja
candidate_id     optional, blank = latest candidate in target Bucket
runtime_variant  optional, blank = catalog default
```

### Job 1: allocate experiment

- targetをRustで解決
- candidate ID指定時は `candidate-NNNNNN` を検証
- 未指定時はBucket listingから `resolve-candidate-location`
- legacy pathを選んだ場合warning
- `experiments` collectionから中央採番

### Job 2: Linux CPU Full Evaluation

`ubuntu-latest`, timeout 360分。

主なflow:

```text
resolve target
fetch/validate revisions
cache HF/model/evaluation assets
fetch candidate
Python ONNX inspection -> generated candidate contract
Rust evaluator capability validation (python-onnx / cpu)
optional reference fetch
Python full evaluator
Rust validate-run
HF Bucketへrun upload (if run-context exists)
成功時benchmark publish
GitHub artifact upload (always)
```

GitHub artifact retentionは7日です。

## 10. `cross-platform-parity.yml`

### Inputs

```text
hf_target
candidate_id (optional)
runtime_variant (optional)
evaluation = smoke | parity | coreml-parity
```

### Matrix

| runner | provider | environment |
|---|---|---|
| ubuntu-latest | CPU | linux |
| windows-latest | CPU | windows |
| macos-15 | CPU | macos |
| macos-15 | CoreML | macos |

Python evaluatorを使って同一candidate/revision contractを比較します。

各matrixでrunをHF Bucketへuploadし、成功時benchmarkをpublishします。GitHub artifact retentionは7日です。

## 11. `rust-eval.yml`

canonical Rust CTC evaluatorの手動matrixです。

### Inputs

```text
hf_target
candidate_id       optional
runtime_variant    optional
evaluation         smoke | parity | coreml-parity | full
strict_provider    boolean, default true
optimization_level configured | disable | basic | extended | all
```

### Matrix

```text
linux-cpu
windows-cpu
windows-directml
macos-cpu
macos-coreml
```

### Preparation boundary

Pythonは次の2箇所に限定されます。

1. `resolve-candidate-artifacts.py` — ONNX graph inspection
2. `prepare-rust-manifest.py` — HF datasets acquisition/materialization

その後:

```text
asr-contracts build-run-context
cargo build -p asr-eval --features <provider>
asr-eval evaluate
asr-contracts validate-run
```

non-CPU + `strict_provider=true` の場合、run-contextへ `--strict-provider` を設定します。

現行workflowは結果をGitHub artifactとして7日保持します。`rust-eval.yml` 自体は `hf-push-run.sh` / benchmark publishを実行しない点に注意してください。

## 12. `provider-strict-probes.yml`

### Trigger

manual dispatchに加え、専用branch `agent/provider-strict-probes` の関連path pushでも起動します。

### Compile/link gate

- Windows: DirectML
- macOS 14: CoreML

release `asr-eval` をprovider feature付きでbuildします。

### Strict runtime probes

synthetic CTC candidateをPython boundaryで生成し、Rustでprovider-specific strict run-contextを作成します。

CoreML:

```text
macos-14
coreml feature
asr-provider-readinessで結果分類
```

DirectML:

```text
windows-latest
directml feature
asr-provider-readinessで結果分類
```

measurement stepは `continue-on-error: true` ですが、後段でexit code/stdout/stderr/resultsを使い **readinessをtruthfulに分類**します。失敗を成功扱いに変えるための設定ではありません。

probe directoryはalways upload、retention 7日です。

## 13. `public-model-e2e.yml`

production Bucket candidateではなく、public model / public datasetを使うreference E2Eです。

### Whisper ONNX + JSUT

- `ubuntu-latest`
- Node 24
- `onnx-community/whisper-small`
- `japanese-asr/ja_asr.jsut_basic5000`
- Hub APIからconcrete revision SHAを解決
- Transformers.js `4.2.0`
- ffmpegでcanonical 16 kHz mono f32 PCMをmaterialize
- real ONNX inference

### Japanese CTC PyTorch -> ONNX -> ORT -> Rust + JSUT

- `ubuntu-latest`
- Python 3.12 + uv
- public Japanese CTC modelをPyTorch/TransformersからONNXへprepare
- Python ORT reference
- generated candidate contract
- Rust `asr-eval` CPU
- Python/Rust transcript parity validation

public-model E2EでのPython model操作はreference/parity boundaryであり、production Rust runtime依存ではありません。

## 14. `rust-release.yml`

### Trigger

- `v*` tag push
- manual dispatch (`tag` input required)

### Build matrix

| artifact | runner | target | features |
|---|---|---|---|
| linux-x86_64 | ubuntu-latest | x86_64-unknown-linux-gnu | cpu |
| windows-x86_64 | windows-latest | x86_64-pc-windows-msvc | cpu,directml |
| macos-aarch64 | macos-15 | aarch64-apple-darwin | cpu,coreml |

生成物:

```text
asr-eval-linux-x86_64.tar.gz
asr-eval-windows-x86_64.zip
asr-eval-macos-aarch64.tar.gz
SHA256SUMS
```

GitHub Releaseが既存ならassetを`--clobber`で置換し、未作成ならgenerate-notes付きで作成します。

## 15. Workflow選択ガイド

| 目的 | 使うworkflow |
|---|---|
| 普通のPR validation | 自動CIに任せる |
| source config / HF routingを確認 | Validate HF Layout |
| production candidateをLinux CPUでfull評価 | CPU Full Evaluation |
| Python runtimeのOS間parity | Cross Platform ONNX Parity |
| Rust CTC runtimeをOS/provider別評価 | Rust Cross Platform Evaluation |
| DirectML/CoreMLでCPU fallbackなしのreadinessを確認 | Provider Strict Probes |
| repository Bucketに依存しないreal model E2E | Public Model E2E |
| Rust binaryを配布 | Rust Release |

## 16. CI結果の解釈

- `rust-ci` green: compile/check/clippy/unit contractがplatform feature上で成立。
- `provider-strict-probes` green: probe workflow自体がreadiness evidenceを正しく生成・分類できた。readiness JSONの中身を確認する。
- `cross-platform-parity` green: Python evaluator pathで選択suiteが各matrix上でacceptanceを満たした。
- `rust-eval` green: Rust CTC evaluatorが指定条件で成立した。
- `public-model-e2e` green: public fixtureに対するreference/parity pathが成立した。

「workflowがgreen」と「acceleratorへ全nodeが割当済み」は同義ではありません。provider evidenceの詳細は [providers.md](./providers.md) を参照してください。
