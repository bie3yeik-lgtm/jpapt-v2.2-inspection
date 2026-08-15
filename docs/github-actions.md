# GitHub Actions 利用ガイド

このドキュメントでは、本リポジトリで利用する Rust 系 GitHub Actions の目的、前提設定、実行方法、成果物、失敗時の確認方法を説明します。

対象 workflow:

- `.github/workflows/rust-ci.yml` — Rust CI
- `.github/workflows/rust-eval.yml` — Rust Cross Platform Evaluation
- `.github/workflows/rust-release.yml` — Rust Release
- `.github/workflows/validate-hf-layout.yml` — Hugging Face 側の前提条件確認

本プロジェクトでは、Python/NeMo を upstream reference・ONNX export・Hugging Face datasets materialization に使用し、Rust を ONNX Runtime 実行・CTC decode・評価・配布 runtime に使用します。

```text
Python / NeMo
├── upstream model/reference
├── ONNX export
└── HF datasets materialization
        │
        ▼
resolved-manifest.json
model.onnx
metadata.json
vocabulary.json
        │
        ▼
Rust
├── audio decode / canonicalization
├── ONNX Runtime inference
├── CTC decode
├── CER / WER
├── benchmark
└── release binary
```

---

## 1. Repository Settings の前提

### Actions Secret

Repository の以下の場所に登録します。

```text
Settings
  → Secrets and variables
    → Actions
      → Secrets
```

必要な Secret:

| 名前 | 用途 |
|---|---|
| `HF_TOKEN` | Hugging Face Bucket / Model Repository へのアクセス |

`HF_TOKEN` はログへ直接出力しないでください。

### Actions Variables

同じ画面の `Variables` に以下を登録します。

| 名前 | 例 | 用途 |
|---|---|---|
| `HF_BUCKET` | `<username>/<bucketname>` | candidate、revision lock、evaluation data の配置先 |
| `HF_MODEL_REPO` | `<username>/<repositoryname>` | validated/released model repository |

workflow 内では次のように参照されます。

```yaml
env:
  HF_TOKEN: ${{ secrets.HF_TOKEN }}
  HF_BUCKET: ${{ vars.HF_BUCKET }}
  HF_MODEL_REPO: ${{ vars.HF_MODEL_REPO }}
```

---

## 2. Hugging Face Bucket の前提

Rust evaluation は GitHub Repository だけでは完結しません。

最低限、HF Bucket に以下が必要です。

```text
hf://buckets/<HF_BUCKET>/
├── config/
│   └── revisions/
│       ├── reference.json
│       ├── evaluation-schema.json
│       └── datasets-lock.json
├── candidates/
│   └── <candidate_id>/
│       ├── *.onnx
│       ├── metadata.json
│       └── vocabulary.json / vocab.json / tokens.json
├── benchmarks/
├── runs/
├── reference/
└── tmp/
```

特に `rust-eval.yml` は以下を前提とします。

```text
config/revisions/reference.json
config/revisions/evaluation-schema.json
config/revisions/datasets-lock.json
candidates/<candidate_id>/*.onnx
candidates/<candidate_id>/metadata.json
candidates/<candidate_id>/<vocabulary JSON>
```

revision lock が不足している場合、評価実行より前の `hf-fetch-revisions.sh` で失敗します。

---

# 3. Rust CI

Workflow:

```text
.github/workflows/rust-ci.yml
```

GitHub Actions 上の表示名:

```text
Rust CI
```

## 実行タイミング

Pull Request で次のファイルが変更された場合に自動実行されます。

```text
Cargo.toml
Cargo.lock
rust/**
.github/workflows/rust-*.yml
```

また、同じ対象ファイルが `main` に push された場合にも実行されます。

## 検証 matrix

現在は次の3環境です。

| Job | Runner | Cargo feature | 主な用途 |
|---|---|---|---|
| `linux-cpu` | `ubuntu-latest` | `cpu` | Linux CPU runtime |
| `windows-directml` | `windows-latest` | `cpu,directml` | Windows DirectML runtime |
| `macos-coreml` | `macos-15` | `cpu,coreml` | Apple Silicon / CoreML EP runtime |

各環境で次を実行します。

```bash
cargo check --workspace --no-default-features --features "<features>"
cargo test --workspace --no-default-features --features "<features>"
```

## rustfmt

別 job として以下も実行されます。

```bash
cargo fmt --all -- --check
```

現在は Rust-first migration 中のため、format 差分は advisory 扱いです。

```yaml
continue-on-error: true
```

したがって、format failure 単独では workflow 全体を失敗させません。

## Cargo / ORT cache

以下を cache します。

```text
~/.cargo/registry
~/.cargo/git
~/.cache/ort.pyke.io
target
```

依存関係や ORT binary の再取得時間を削減するためです。

## `resolved-cargo-lock` artifact

`linux-cpu` job は、CI中に実際に解決された `Cargo.lock` を以下の artifact 名で保存します。

```text
resolved-cargo-lock
```

保持期間は1日です。

GitHub UI:

```text
Actions
  → Rust CI
    → 対象 run
      → Artifacts
        → resolved-cargo-lock
```

現時点では Repository root の `Cargo.lock` は bootstrap placeholder です。そのため、完全な reproducible build に移行する際は、この生成済み lockfile を commit し、CI/Release を `--locked` に切り替えることを推奨します。

---

# 4. Rust Cross Platform Evaluation

Workflow:

```text
.github/workflows/rust-eval.yml
```

表示名:

```text
Rust Cross Platform Evaluation
```

これは自動実行ではなく、`workflow_dispatch` による手動評価 workflow です。

## GitHub UI からの起動

```text
GitHub Repository
  → Actions
    → Rust Cross Platform Evaluation
      → Run workflow
```

入力項目:

### `candidate_id`

必須です。

例:

```text
ctc-fp32-20260816-001
```

この値は次の Bucket path に対応します。

```text
hf://buckets/<HF_BUCKET>/candidates/ctc-fp32-20260816-001/
```

### `evaluation`

以下から選択します。

```text
smoke
parity
coreml-parity
full
```

既定値:

```text
smoke
```

推奨順序:

```text
smoke
  ↓
parity
  ↓
coreml-parity
  ↓
full
```

最初から `full` を実行するより、まず `smoke` で runtime contract と candidate 構成を確認してください。

## Evaluation matrix

| Job | OS | Provider | Cargo feature |
|---|---|---|---|
| `linux-cpu` | Ubuntu | CPU | `cpu` |
| `windows-cpu` | Windows | CPU | `cpu` |
| `macos-cpu` | macOS 15 | CPU | `cpu` |
| `macos-coreml` | macOS 15 | CoreML | `cpu,coreml` |

DirectML は CI compile/test の対象ですが、現在の cross-platform evaluation matrix には含めていません。

## Workflow 内部処理

概略は次の通りです。

```text
1. Repository checkout
2. Python 3.12 setup
3. Python preparation layer install
4. HF revision locks download
5. candidate download
6. locked dataset selection materialization
7. candidate ONNX / vocabulary discovery
8. Rust asr-eval release build
9. Rust evaluation
10. JSON contract validation
11. result artifact upload
```

### Python preparation layer

以下をインストールします。

```bash
python -m pip install -e ".[datasets,onnx,dev]"
python -m pip install --upgrade huggingface_hub
```

Python はここで、HF dataset の解決と materialization を担当します。

### Revision lock の取得

```bash
bash scripts/hf/hf-fetch-revisions.sh
```

### Candidate の取得

```bash
bash scripts/hf/hf-fetch-candidate.sh "<candidate_id>"
```

### Rust 用 resolved manifest の生成

```bash
python scripts/ci/prepare-rust-manifest.py \
  --provider "<provider>" \
  --evaluation "<evaluation>" \
  --environment "<environment>" \
  --revisions .ci/hf/config/revisions \
  --output .ci/resolved-manifest.json
```

ここが Python → Rust の明確な境界です。

Rust 側は Hugging Face `datasets` object を直接扱わず、materialize 済み local audio path を含む resolved manifest を読みます。

### Candidate asset discovery

workflow は candidate directory から最初の ONNX を検索します。

```text
*.onnx
```

vocabulary は以下のいずれかを検索します。

```text
vocabulary.json
vocab.json
tokens.json
```

どちらかが見つからない場合は評価開始前に失敗します。

### Rust evaluator build

```bash
cargo build --release \
  -p asr-eval \
  --no-default-features \
  --features "<features>"
```

### Evaluation 実行

概念的には以下です。

```bash
asr-eval evaluate \
  --provider <provider> \
  --model <candidate.onnx> \
  --candidate-dir .ci/candidate \
  --candidate-id <candidate_id> \
  --vocabulary <vocabulary.json> \
  --resolved-manifest .ci/resolved-manifest.json \
  --evaluation <suite> \
  --revisions .ci/hf/config/revisions \
  --output results/<platform>
```

## Evaluation の成果物

各 matrix job は、成功・失敗にかかわらず可能な範囲で結果を artifact にします。

artifact 名:

```text
rust-eval-<matrix-name>-<candidate_id>
```

例:

```text
rust-eval-linux-cpu-ctc-fp32-20260816-001
rust-eval-macos-coreml-ctc-fp32-20260816-001
```

保持期間:

```text
7 days
```

結果 directory には主に以下が生成されます。

```text
results/<matrix-name>/
├── run-context.json
├── samples.jsonl
└── metrics.json
```

`metrics.json` が存在する場合、workflow は以下で schema / shared contract を確認します。

```bash
python scripts/ci/validate-result.py "results/<matrix-name>"
```

---

# 5. Rust Release

Workflow:

```text
.github/workflows/rust-release.yml
```

表示名:

```text
Rust Release
```

## 自動 Release

`v` で始まる Git tag を push すると起動します。

例:

```bash
git tag v0.1.0
git push origin v0.1.0
```

trigger:

```yaml
on:
  push:
    tags:
      - "v*"
```

## 手動 Release

GitHub UI:

```text
Actions
  → Rust Release
    → Run workflow
```

`tag` に以下のような値を入力します。

```text
v0.1.0
```

`v` で始まらない値は workflow が拒否します。

## Build matrix

| Release asset | Runner | Target | Feature |
|---|---|---|---|
| Linux x86_64 | Ubuntu | `x86_64-unknown-linux-gnu` | `cpu` |
| Windows x86_64 | Windows | `x86_64-pc-windows-msvc` | `cpu,directml` |
| macOS Apple Silicon | macOS 15 | `aarch64-apple-darwin` | `cpu,coreml` |

CUDA feature 自体は Rust runtime に存在しますが、GitHub-hosted runner 上で CUDA runtime を検証していないため、自動 Release binary matrix には含めていません。

## Release binary build

各 target について以下を実行します。

```bash
cargo build --release \
  -p asr-eval \
  --no-default-features \
  --features "<features>" \
  --target "<target>"
```

## Release asset

生成される archive:

```text
asr-eval-linux-x86_64.tar.gz
asr-eval-windows-x86_64.zip
asr-eval-macos-aarch64.tar.gz
SHA256SUMS
```

Unix archive 内:

```text
asr-eval
```

Windows archive 内:

```text
asr-eval.exe
```

## SHA256SUMS

全 build artifact を集約した後、以下で checksum を生成します。

```bash
sha256sum asr-eval-* > SHA256SUMS
```

利用者は download 後に checksum を検証できます。

Linux/macOS の例:

```bash
sha256sum -c SHA256SUMS
```

## GitHub Release の作成

workflow は GitHub CLI を使用します。

新規 tag の場合:

```bash
gh release create "$TAG" \
  --target "$TARGET" \
  --generate-notes \
  --title "$TAG"
```

同名 Release がすでにある場合は、既存 Release を保持したまま asset を `--clobber` で差し替えます。

Release workflow は以下の permission を持ちます。

```yaml
permissions:
  contents: write
```

追加の Personal Access Token は不要で、GitHub Actions の `github.token` を使用します。

---

# 6. 推奨 Release 手順

モデル/runtimeの検証を伴う通常の release では、次の順序を推奨します。

```text
1. Candidate を HF Bucket candidates/<candidate_id>/ に配置
2. revision lock を確認
3. Rust Cross Platform Evaluation / smoke
4. parity
5. macOS CoreML が対象なら coreml-parity
6. 必要に応じて full
7. 結果 artifact を確認
8. main に必要な変更を merge
9. version tag を作成
10. v* tag push
11. Rust Release 完了を確認
12. GitHub Release の asset / SHA256SUMS を確認
```

例:

```bash
git switch main
git pull --ff-only

git tag v0.1.0
git push origin v0.1.0
```

タグを push した時点で Release workflow が起動するため、評価前に tag を作らないことを推奨します。

---

# 7. GitHub UI での結果確認

## CI

```text
Repository
  → Actions
    → Rust CI
```

または Pull Request の Checks から確認します。

見るべき job:

```text
linux-cpu
windows-directml
macos-coreml
rustfmt advisory
```

## Evaluation

```text
Repository
  → Actions
    → Rust Cross Platform Evaluation
      → Run
        → Artifacts
```

## Release

workflow:

```text
Repository
  → Actions
    → Rust Release
```

完成物:

```text
Repository
  → Releases
```

---

# 8. 主な失敗パターン

## `reference.json` が見つからない

例:

```text
file(s) not found in bucket:
config/revisions/reference.json
```

原因:

```text
HF Bucket の revision lock が未配置
```

Rust compile failure ではありません。

HF Bucket の以下を確認してください。

```text
config/revisions/reference.json
config/revisions/evaluation-schema.json
config/revisions/datasets-lock.json
```

## `No ONNX model found`

candidate directory に `*.onnx` がありません。

確認先:

```text
hf://buckets/<HF_BUCKET>/candidates/<candidate_id>/
```

## `No vocabulary JSON found`

以下のどれかが必要です。

```text
vocabulary.json
vocab.json
tokens.json
```

## CoreML job のみ失敗する

CPU job が成功し CoreML job だけ失敗する場合は、単純な model failure と CoreML EP 固有 failure を分けて確認します。

関連分類:

```text
COREML_PROVIDER_UNAVAILABLE
COREML_SESSION_REGISTRATION_FAILED
COREML_GRAPH_SHAPE_INCOMPATIBLE
COREML_GRAPH_COMPILATION_FAILED
COREML_RUNTIME_EXECUTION_FAILED
COREML_UNEXPECTED_CPU_FALLBACK
COREML_NUMERICAL_PARITY_FAILED
```

## Windows DirectML CI のみ失敗する

`rust-ci.yml` の Windows job は以下 feature で build/test します。

```text
cpu,directml
```

まず Rust compile error か ONNX Runtime / provider dependency error かを job log で切り分けてください。

## Release は成功したが runtime 実行が保証されない

Release workflow が保証するのは、指定 target と feature の binary build/package が成功したことです。

実モデルでの精度・provider parity は `rust-eval.yml` の責務です。

したがって、Release workflow の成功だけを model promotion の acceptance gate にしないでください。

---

# 9. Workflow ごとの責務

```text
validate-hf-layout.yml
    ↓
HF / repository 前提条件の確認

rust-ci.yml
    ↓
Rust source の compile / unit test / platform feature確認

rust-eval.yml
    ↓
実 candidate + 実 evaluation data による runtime correctness / parity

rust-release.yml
    ↓
validated source から配布 binary を生成して GitHub Release を作成
```

重要なのは、これらを一つの workflow として扱わないことです。

```text
CI success
≠ model parity success
≠ release acceptance
```

本プロジェクトでは、最終的な model promotion / release acceptance 条件は locked `evaluation-schema.json` を authoritative source として扱う設計です。
