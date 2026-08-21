# GitHub Actions

この文書は `.github/workflows/` の現行YAMLを基準に、GitHub Actions全体の役割、trigger、input、権限、成果物、workflow間の関係をまとめます。

操作性・外部dispatchの設計判断は [github-actions-ux.md](./github-actions-ux.md)、共通repository dispatch APIは [repository-dispatch.md](./repository-dispatch.md)、GHCR固有の詳細は [ghcr-ci.md](./ghcr-ci.md) を参照してください。

## 1. 基本原則

GitHub Actionsはruntime semanticsのsource of truthではありません。workflowは以下の正規contractを呼び出すexecution/orchestration layerです。

```text
config/asr-catalog.json
config/hf-targets/*.toml
config/models/*.toml
config/providers/*.toml
config/environments/*.toml
config/evaluation/*.toml
config/evaluators/*.toml
evaluation/schemas/*.schema.json
Dockerfile labels
Rust CLI
Python-native ML/dataset boundary
official hf / gh CLI
```

workflow YAMLへcandidate prefix、decoder mapping、artifact role、Bucket path rule、allocation prefix、独自target routing tableを再実装しません。

`workflow_dispatch.inputs` はGitHub UI/manual APIでのinput schemaの正本です。外部`repository_dispatch`向けに別の入力catalog JSONは持ちません。Rust `asr-workflow-dispatch` がworkflow YAMLを読み、外部dispatchを同じcontractへ正規化します。

## 2. Workflow一覧

正確なdispatch対象一覧は手書きの文書ではなく次で取得できます。

```bash
mise run actions-list
```

現行workflowの役割は次です。

| Workflow | 主なtrigger | 主目的 |
|---|---|---|
| `python-unit.yml` | PR / main push / manual | Python locked environmentとunit tests |
| `rust-ci.yml` | PR / main push / manual | Rust fmt/check/clippy/testを3 OSで検証 |
| `validate-hf-layout.yml` | PR / main push / manual | source-controlled config/HF layout validation |
| `capsule-interop.yml` | PR / main push / manual | Rust→Python ExperimentCapsuleV1 interop |
| `ghcr-contracts.yml` | PR / main push / manual | Docker/HF/Actions/dispatchの高速contract gate |
| `ghcr-build-publish.yml` | Docker関連PR / main push / manual | NeMo環境build、mainでGHCR publish/attestation |
| `ghcr-evaluate.yml` | manual / schedule / successful GHCR build | digest-pinned GHCR CPU evaluation→HF Bucket |
| `ghcr-audit.yml` | manual / schedule | live GHCR package audit |
| `repository-dispatch.yml` | repository_dispatch / manual | 外部要求をRust検証後に対象workflowへroute |
| `cpu-full-eval.yml` | manual | Python Linux CPU full evaluation→HF run/benchmark |
| `cross-platform-parity.yml` | manual | Python evaluatorのOS/provider parity |
| `rust-eval.yml` | manual | canonical Rust CTC evaluator matrix |
| `provider-strict-probes.yml` | manual /限定branch push | CoreML strict readiness evidence |
| `public-model-e2e.yml` | manual /限定branch push | public model/dataset reference E2E |
| `hf-central-allocator.yml` | manual / workflow dispatch | candidate/experiment/config中央採番 |
| `rust-release.yml` | `v*` tag / manual | Rust binary build + GitHub Release |

`repository-dispatch.yml` 自身を除く全workflowは `workflow_dispatch` を持ち、共通routerから起動可能です。`ghcr-contracts.yml` がこの不変条件をRustで検証します。

## 3. 共通repository dispatch

外部システムはworkflowごとの独自event typeを覚える必要はありません。

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "ghcr-evaluate",
    "ref": "main",
    "inputs": {
      "target": "parakeet-tdt_ctc-0.6b-ja"
    }
  }
}
```

`workflow` は `.yml` filenameまたはfilename stem aliasを受け付けます。

routerはRust `asr-workflow-dispatch` を使って、heavy job起動前に以下を検証します。

- workflow存在/alias解決
- `workflow_dispatch`対応
- required input
- YAML default補完
- unknown input拒否
- `choice`検証
- boolean型検証
- Git refの安全性
- GitHub workflow-dispatch API body生成

router runには要求workflow/refを含むdynamic `run-name` が付き、正規化後のinputは`GITHUB_STEP_SUMMARY`へ出力されます。

ローカル確認:

```bash
mise run actions-list
mise run actions-validate
mise run actions-ghcr
```

## 4. Secrets / variables / permissions

### `HF_TOKEN`

HF Bucket/Model Repoのread/write、revision/candidate fetch、run/benchmark upload、central allocationに使用します。

主な利用workflow:

```text
validate-hf-layout.yml (manual selected-target lane)
cpu-full-eval.yml
cross-platform-parity.yml
rust-eval.yml
ghcr-evaluate.yml
hf-central-allocator.yml
```

### `HF_TARGETS_JSON`

repository variableです。GHCR CIでDockerfileとsource-controlled targetを照合するためのchecked routing snapshotとして使用します。

独立したruntime authorityではありません。variable-only entryはsource-controlled targetを生成しません。

### GHCR authentication

GHCRはrepository Package workflow permission + `${{ github.token }}` のみを使います。

read lane:

```yaml
permissions:
  contents: read
  packages: read
```

publish lane:

```yaml
permissions:
  contents: read
  packages: write
  attestations: write
  id-token: write
```

PAT fallbackはありません。`SUPERSECRET`はGHCR workflowでは使用しません。

### `HF_ALLOCATOR_GITHUB_TOKEN`

既存評価workflowがcentral allocatorをGitHub API経由でdispatchする場合に使用します。未設定時はworkflowの`github.token` fallbackを利用する既存設計です。

### 最小権限

- 通常CI: `contents: read`
- repository dispatch router: `contents: read`, `actions: write`
- allocatorを呼ぶworkflow: 必要な`actions: write`
- GHCR read: `packages: read`
- GHCR publish: `packages: write`, attestation用権限
- release: `contents: write`

## 5. `python-unit.yml`

Python compatibility/reference boundaryの標準CIです。

### Environment

```text
runner: ubuntu-latest
Python: 3.12
uv locked environment
onnxruntime: 1.28.0
```

### Flow

```bash
uv lock --check
uv sync --locked --extra datasets --extra onnx --extra dev
uv run python -m pytest -q python/tests/unit
```

Python-native model/dataset/tooling boundaryを検証します。Rust production policyの代替ではありません。

## 6. `rust-ci.yml`

Rust workspaceの標準CIです。

### Matrix

| lane | runner | feature |
|---|---|---|
| Linux CPU | `ubuntu-latest` | `cpu` |
| macOS CoreML | `macos-15` | `cpu,coreml` |

各laneで:

```bash
cargo metadata --locked --no-deps --format-version 1
cargo check --locked --workspace --no-default-features --features <features>
cargo clippy --locked --workspace --all-targets --no-default-features --features <features> -- -D warnings
cargo test --locked --workspace --no-default-features --features <features>
```

`cargo fmt --all -- --check` は独立jobです。

provider featureのcompile/link/unit testを証明しますが、real accelerator execution proofではありません。

## 7. `validate-hf-layout.yml`

source-controlled contractとHF layoutの標準validationです。

主要項目:

- locked Python project
- repository doctor/Python boundary validation
- `asr-hf validate-targets`
- GitHub Action version policy
- ASR catalog fingerprint
- collection-derived allocation prefix
- legacy allocation catalog不在
- revision bundle validation
- HF shell syntax/focused tests
- manual dispatch時のselected target/Bucket validation

`docs/**`変更も監視するため、文書だけが実装から乖離することを防ぎます。

## 8. `capsule-interop.yml`

Rust producer→Python consumerの`ExperimentCapsuleV1`互換性を検証します。

```text
Rust write_fixture
  ↓
run.parquet
  ↓
Python read_experiment_capsule / summarize_experiment_capsule
  ↓
run ID / metric / diagnostic metadata assertions
```

## 9. `ghcr-contracts.yml`

GHCR関連の最も軽量なpreflight gateです。

検証内容:

- Dockerfile mandatory labels
- Docker config source identity
- Dockerfile→source-controlled HF target mapping
- `HF_TARGETS_JSON`との一致
- `asr-hf validate-targets`
- GitHub Action version policy
- Rust `asr-workflow-dispatch validate`
- 全workflowのdispatch reachability
- default GHCR dispatch requestのresolve smoke

重いimage buildやmodel downloadより先に失敗させることが目的です。

## 10. `ghcr-build-publish.yml`

NVIDIA NeMo reference/export environmentをbuild/publishします。

### PRコスト制御

GitHubのPR path filterだけでは、PRに一度Docker変更が入ると後続のdocs-only synchronizeでもworkflow runが作られ得ます。そのためworkflow自身が前回PR head→現在headを比較します。

```text
Dockerfile / build workflowに差分なし
  -> lightweight gateのみ

差分あり
  -> Buildx
```

concurrencyはworkflow全体ではなくheavy `build` jobだけに設定します。docs-only synchronizeはgroupへ入らず実行中buildを妨害しません。一方、新しい実Docker変更による同一package buildは旧build jobをcancelできます。

### PR Buildx

```text
push=false
load=false
```

import/version smokeはDockerfile最終`RUN`に組み込まれています。巨大imageをDocker daemonへexportする必要はありません。

### main/manual publish

```text
Buildx build
  -> integrated environment smoke
  -> GHCR push
  -> digest validation
  -> artifact attestation
  -> build provenance artifact
```

push直後の再pullは行いません。live registry verificationは`ghcr-audit.yml`、実行検証は`ghcr-evaluate.yml`の責務です。

## 11. `ghcr-evaluate.yml`

GHCR environmentを実際のcandidate評価へ接続するworkflowです。

### Inputs

```text
target          optional; blank = matching targets
candidate_id    optional; blank = latest compatible candidate
runtime_variant optional; blank = target/catalog default
evaluation      smoke | parity | full
image_tag       default latest
```

### Flow

```text
Docker/HF target matrix
  ↓
revision bundle fetch/validation
  ↓
candidate resolve/fetch
  ↓
experiment ID allocation
  ↓
GHCR login/pull
  ↓
tag -> RepoDigest freeze
  ↓
image identity validation
  ↓
digest-pinned docker run
  ↓
Python CPU evaluator
  ↓
Rust validate-run
  ↓
HF Bucket run upload
  ↓
GHCR-specific benchmark publish
```

Project sourceは`PYTHONPATH=/workspace/python/src`でbind-mounted repositoryから読み、pulled imageへruntime pip installしません。

## 12. `ghcr-audit.yml`

live GHCR packageの定期/手動監査です。

主な検査:

- pull + digest freeze
- mandatory OCI/project labels
- source URL
- GitHub artifact attestation
- NeMo/PyTorch/ONNX/ORT/HF等のimport
- ORT/HF pin
- `pip check`
- Docker inspect/history evidence

build workflowが省略した「registryへ保存された実物」の確認をここで担います。

## 13. `cpu-full-eval.yml`

Python ONNX evaluatorによるLinux CPU full評価です。

Inputs:

```text
hf_target
candidate_id     optional
runtime_variant  optional
```

未指定candidateはBucket listingから自動解決します。

Flow:

```text
target/candidate resolve
  -> experiment allocation
  -> revisions
  -> candidate fetch
  -> Python ONNX inspection
  -> Rust evaluator-policy validation
  -> Python full evaluation
  -> Rust validate-run
  -> HF run upload
  -> benchmark publish
```

## 14. `cross-platform-parity.yml`

Python evaluatorによるplatform/provider parityです。

Matrix:

```text
Linux CPU
Windows CPU
macOS CPU
macOS CoreML
```

同一candidate/revision identityを比較し、各runをHF Bucketへ保存します。

## 15. `rust-eval.yml`

canonical Rust CTC evaluatorです。

Matrix:

```text
Linux CPU
Windows CPU
Windows provider routes
macOS CPU
macOS CoreML
```

PythonはONNX graph inspectionとHF dataset materialization境界に限定され、その後はRust run-context/runtime/metrics/evaluationを使用します。

## 16. `provider-strict-probes.yml`

CoreMLについて「featureがcompileする」だけでなくstrict provider readinessを分類します。DirectMLはretiredでありprobe対象外です。

- macOS: CoreML
- synthetic provider probe fixture
- Rust provider-specific run context
- Rust readiness classification
- stdout/stderr/results evidence upload

measurement failureを成功扱いにはせず、証拠からclassificationします。

## 17. `public-model-e2e.yml`

production candidateとは別のpublic reference laneです。

代表経路:

```text
public Whisper ONNX + JSUT
public Japanese CTC PyTorch -> ONNX -> Python ORT -> Rust + JSUT
```

model export/reference parityでPythonを使うことはRust-first retention policy上の許可された境界です。

## 18. `hf-central-allocator.yml`

Bucket内のsequence IDを直列化して割り当てます。

Collections:

```text
candidates  -> candidate-NNNNNN
experiments -> experiment-NNNNNN
config      -> config-NNNNNN
```

prefixはcollectionからRustで導出し、allocation catalog/prefix-key JSONは使用しません。

同一Bucketについてconcurrencyを直列化し、response schema v4の最小allocation JSONを返します。

## 19. `rust-release.yml`

`asr-eval` release binaryをbuildします。

| artifact | runner | provider feature |
|---|---|---|
| Linux x86_64 | Ubuntu | CPU |
| Windows x86_64 | Windows | CPU |
| macOS arm64 | macOS | CPU + CoreML |

生成物と`SHA256SUMS`をGitHub Releaseへ公開します。

## 20. Workflow選択ガイド

| 目的 | Workflow |
|---|---|
| 普通のPR validation | 自動Python/Rust/HF/interop CI |
| HF/config contractだけ確認 | `validate-hf-layout.yml` |
| Docker/HF/dispatch contract確認 | `ghcr-contracts.yml` |
| NeMo reference environment build/publish | `ghcr-build-publish.yml` |
| GHCR上の環境で最新candidateを評価 | `ghcr-evaluate.yml` |
| GHCR package自体を監査 | `ghcr-audit.yml` |
| Linux CPU production full | `cpu-full-eval.yml` |
| Python OS/provider parity | `cross-platform-parity.yml` |
| Rust CTC runtime matrix | `rust-eval.yml` |
| CoreML strict proof | `provider-strict-probes.yml` |
| public model reference E2E | `public-model-e2e.yml` |
| Rust binary release | `rust-release.yml` |
| 外部システムから任意workflow実行 | `repository-dispatch.yml` / `jpapt.workflow` |

## 21. 新規workflow追加時の必須条件

1. router自身以外は`workflow_dispatch`を持つ。
2. model-independent input validationはRust/source-controlled contractへ寄せる。
3. stable defaultはYAML default、dynamic defaultはruntime resolverを使う。
4. target/candidate/variant一覧をworkflowへ重複保持しない。
5. heavy work前にfast validationを置く。
6. mutable tag/pathを実験identityにしない。
7. failure diagnosisに有用なartifact/step summaryを残す。
8. repository dispatchから到達可能にする。
9. GitHub UIで実装できない制約は[github-actions-ux.md](./github-actions-ux.md)へ記録する。
10. `mise run actions-validate` と通常CIを通す。
