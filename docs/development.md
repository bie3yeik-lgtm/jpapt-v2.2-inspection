# Development Environment

この文書は、現在のrepositoryをローカルで開発・検証するときの環境を `mise.toml`, `pyproject.toml`, `Cargo.toml`, GitHub Actions に合わせて説明します。

## 1. Toolchain

`mise.toml` の現行値:

```toml
python = "3.14"
uv = "latest"
rust = "1.97.1"
node = "26"
pnpm = "11.20.0"
go = "1.26"
```

Python package自体のsupported rangeは `pyproject.toml` で `>=3.12,<3.15` です。GitHub Actionsは再現性とecosystem compatibilityのため多くのjobでPython 3.12を使用します。したがって「local defaultが3.14」「CIが3.12」は矛盾ではありません。

Rust workspaceはedition 2024 / resolver 3です。

## 2. Repository-local cache

miseはrepository root配下へcacheを寄せます。

```text
.cache/
├── huggingface/   # HF_HOME
├── uv/            # UV_CACHE_DIR
└── pnpm/          # PNPM_STORE_DIR
```

環境変数:

```text
PARAKEET_ONNX_REPO_ROOT=<repo-root>
HF_HOME=<repo-root>/.cache/huggingface
UV_CACHE_DIR=<repo-root>/.cache/uv
PNPM_STORE_DIR=<repo-root>/.cache/pnpm
```

CIはworkflowごとに必要なcacheだけを `actions/cache` で保持します。candidate/revision/run identityそのものをcacheへ依存させてはいけません。

## 3. 初期セットアップ

miseを使用する場合:

```bash
mise install
mise run setup
mise run doctor
```

OS別setupはmise taskから次へ委譲されます。

```text
Windows -> scripts/dev/setup.ps1
Linux/macOS -> scripts/dev/setup.sh
```

`mise run doctor` は `uv run python scripts/dev/doctor.py` を実行します。

## 4. Python環境

Python packageは `parakeet-onnx` です。

locked development environment:

```bash
uv lock --check
uv sync --locked --extra datasets --extra onnx --extra dev
```

用途別extra:

| extra | 主用途 |
|---|---|
| `datasets` | Hugging Face dataset取得/materialization |
| `onnx` | ONNX inspection / Python ORT |
| `hf` | pinned Hugging Face Hub client |
| `transformers-runtime` | Whisper等のruntime support |
| `transformers` | PyTorch/Transformersを使うexport/reference E2E |
| `dev` | pytest / Ruff / mypy |
| `tools` | ONNX tooling |

Python ORTは `onnxruntime==1.28.0` にpinされています。CIはこのversionを明示検証します。

主なPython CLI:

```text
parakeet-onnx-export
parakeet-onnx-evaluate
parakeet-onnx-compare
parakeet-onnx-benchmark
```

## 5. Rust環境

workspace member:

```text
asr-runtime
asr-audio
asr-metrics
asr-eval
asr-capsule
asr-contracts
asr-hf
```

基本確認:

```bash
cargo metadata --locked --no-deps --format-version 1 >/dev/null
cargo fmt --all -- --check
cargo check --locked --workspace
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
```

provider featureを指定する場合:

```bash
# Linux CPU
cargo check --locked --workspace --no-default-features --features cpu

# Windows DirectML
cargo check --locked --workspace --no-default-features --features "cpu,directml"

# macOS CoreML
cargo check --locked --workspace --no-default-features --features "cpu,coreml"
```

release binary:

```bash
cargo build --locked --release -p asr-eval --no-default-features --features cpu
```

## 6. mise tasks

現在の代表task:

```bash
mise run setup
mise run doctor
mise run hf-revisions
mise run test
mise run lint
mise run format
mise run rust-check
```

`mise run format` はPython側をRuff、Rust側をrustfmtでformatします。

## 7. Hugging Face認証

HF Bucket/Model Repoへアクセスする処理では `HF_TOKEN` が必要です。

ローカル例:

```bash
export HF_TOKEN=...
```

GitHub Actionsではrepository secret `HF_TOKEN` を使用します。central allocatorをworkflowからdispatchする処理は、必要に応じて `HF_ALLOCATOR_GITHUB_TOKEN` を使い、未設定時は `github.token` をfallbackとして使用します。

secretをconfig TOML、JSON、docs、workflow inputへ直接保存してはいけません。

## 8. HF target解決

human/operatorが指定する基本入力はtarget IDです。

```bash
cargo run --quiet --locked -p asr-hf -- \
  resolve-target --target parakeet-tdt_ctc-0.6b-ja
```

resolverが以下を導出します。

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

runtime variantを省略するとASR catalogのdefault variantを使用します。

## 9. Revision configの取得

```bash
export HF_TARGET_ID=parakeet-tdt_ctc-0.6b-ja
# 通常はresolve-targetでHF_BUCKET等も設定する
bash scripts/hf/hf-fetch-revisions.sh
```

local materialization:

```text
.ci/hf/config/
├── current.json
├── resolved.json
└── revisions/
    ├── reference.json
    ├── evaluation-schema.json
    ├── datasets-lock.json
    └── runtime.json
```

`HF_CONFIG_VERSION=config-NNNNNN` を明示した場合はcurrent pointerではなくoverrideを使用します。

## 10. Candidateの取得

```bash
bash scripts/hf/hf-fetch-candidate.sh candidate-000001
```

fetch先ではBucket identityを表す `.candidate-id` がmaterializeされます。source candidateへ `.candidate-id` を事前に置いてpublishしてはいけません。

candidate IDを省略するworkflowでは、`hf buckets list` の結果を `asr-hf resolve-candidate-location` へ渡して自動解決します。

## 11. Candidate contract

Python-native ONNX inspection boundary:

```bash
python scripts/ci/resolve-candidate-artifacts.py \
  --candidate-dir .ci/candidate \
  --runtime-variant ctc \
  --contract-out .ci/candidate-contract.json
```

このPython処理はONNX graph/tooling boundaryです。生成されたcandidate contract以降のstable policyはRust側でも検証します。

## 12. Rust evaluatorのローカル実行概念

Rust pathではdataset acquisition/materializationだけPython boundaryを通します。

```text
HF revisions
    + candidate
    + Python ONNX inspection
    + Python datasets materialization
            ↓
GeneratedCandidateContract
ResolvedManifest
            ↓
Rust build-run-context
            ↓
asr-eval evaluate
            ↓
run-context.json / samples.jsonl / metrics.json / run.parquet
```

Rust evaluatorは現在CTCのみを受理します。TDT/Whisperを指定するとcapability policyでfailします。

## 13. OS別の役割

### Linux

- CPU reference/evaluation
- Python Unit / HF Layout / public-model E2Eの主要環境
- CUDAはprovider config/runtimeが対応するが、標準Rust CI matrixには現時点で含めない

### Windows

- CPU + DirectML
- `rust-ci.yml` では `cpu,directml`
- strict DirectML readinessは `provider-strict-probes.yml`

### macOS

- CPU + CoreML
- `rust-ci.yml` は `macos-15`, `cpu,coreml`
- strict CoreML probeは現在 `macos-14`
- CoreMLのcompile/session/runtime failureを別々に分類する

## 14. ローカル変更前の推奨確認

Pythonだけ:

```bash
uv lock --check
uv run python -m pytest -q python/tests/unit
uv run ruff check python scripts
```

Rustだけ:

```bash
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
```

config/schema/HF scriptsを触る場合:

```bash
mise run doctor
cargo run --quiet --locked -p asr-hf -- validate-targets
cargo run --quiet --locked -p asr-contracts --bin asr-action-policy
bash -n scripts/hf/*.sh
```

最終的なPR validation範囲は変更pathに応じてGitHub Actionsが決めます。詳細は [github-actions.md](./github-actions.md) を参照してください。
