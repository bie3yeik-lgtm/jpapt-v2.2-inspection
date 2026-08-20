# 親リポジトリ external-dispatch 向け GitHub Actions 実装ブランチ

作成日: 2026-08-20
対象ブランチ: `feat/parent-external-dispatch-workflows`
親リポジトリ: [`largoyo/Premiere-AutoProcess-Plugin`](https://github.com/largoyo/Premiere-AutoProcess-Plugin)
公開正本: [`bie3yeik-lgtm/jpapt-v2.2-inspection`](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection)
着手時点の `main` SHA: `5d4974fb8e10b04088a419e37545b1e5cedd900e`

## 1. ブランチの目的

親リポジトリ `largoyo/Premiere-AutoProcess-Plugin` は Private Actions Billing に依存しない方針のため、新しい実行用 GitHub Actions を親側へ追加せず、HF Bucket・GHCR・HF Jobs・provider evaluation・candidate lifecycle・upstream inspection などの実行を、公開正本 `bie3yeik-lgtm/jpapt-v2.2-inspection` へ `repository_dispatch` する。

本ブランチの目的は、親リポジトリが dispatch して解決すべき workflow を、公開正本側に実装し、`repository_dispatch` router（[`repository-dispatch.yml`](../.github/workflows/repository-dispatch.yml) / Rust `asr-workflow-dispatch`）から呼び出せる状態にすることである。

親側の route table と caller dispatcher は次を正本とする。

- [`TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-github-actions-external-dispatch-migration.md`](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-github-actions-external-dispatch-migration.md)
- [`TelopFlow_Feature/TF-v1-onnx-implements/config/jpapt-external-dispatch.v1.json`](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/config/jpapt-external-dispatch.v1.json)
- `scripts/jpapt-external-dispatch.py`（親リポジトリ側 caller）

本 repository では workflow YAML、Rust contract test、receipt schema、関連 docs を source-controlled 正本として追加・更新する。親 repository へ新しい実行 workflow を追加しない。

## 2. 関連 issue と責務

| 親 issue | 本ブランチでの扱い | 主な dispatch / workflow 関係 |
|---|---|---|
| [#134](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/134) Parakeet provenance | asset inventory・immutable revision・candidate transfer mapping は親/operator 側。本 repo は provenance schema、routing gate、upstream contract diff route を担当 | `candidate-routing-config-fetch` は partial。full contract diff route は **upstream-required** |
| [#154](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/154) package artifact/run identity | public Gateway + HF Jobs smoke は **available**。private trusted artifact 検証は **blocked** | `jpapt.candidate-request` → `candidate-request-gateway` |
| [#160](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/160) GHCR anonymous pull | `verify-public` 相当は **upstream-required**。現行は `ghcr-audit` + caller 側 anonymous preflight の partial 迂回 | `jpapt.workflow` → `ghcr-audit`（partial）、将来 `ghcr-public-verify` |

issue 間の依存順序（親側 resolution plan より）:

```text
#134 provenance inventory / manifest
  -> #160 GHCR namespace readiness / real package
    -> #154 artifact/run identity
      -> Parquet capsule + JPAPT dispatch/completion/ACK/lifecycle E2E
        -> issue close review
```

## 3. 親リポジトリ migration 文書の実装対象一覧

親 [`jpapt-github-actions-external-dispatch-migration.md`](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-github-actions-external-dispatch-migration.md) の workflow 別迂回路と、本ブランチで扱う公開正本側の作業を対応づける。

| 親 local workflow | dispatch route | 状態 | 本ブランチでの作業 |
|---|---|---|---|
| `ghcr-package-provision.yml` | `jpapt.workflow` → `ghcr-audit` | partial | **`ghcr-public-verify` workflow を新規実装**（匿名 registry API のみ、GHCR login なし） |
| `hf-model-bootstrap-package.yml` | `jpapt.bucket-bootstrap` → `external-bucket-bootstrap` | available | 既存 workflow の contract 確認。必要なら receipt 強化のみ |
| `hf-model-pipeline.yml` | `jpapt.candidate-request` → `candidate-request-gateway` | retired | 新規実装不要。Gateway contract を正本とする |
| `fixture-generation-and-inspection.yml` | `hf-jobs-smoke` 候補 | upstream-required | **`fixture-generation-and-inspection` workflow を新規実装** |
| `jpapt-private-dispatch.yml` | `jpapt.candidate-request` → `candidate-request-gateway` | available | 既存 Gateway。`scripts/ci/dispatch-public-inspection-bypass.sh` で plan/execute 分離 |
| `jpapt-package-artifact-verify.yml` | `private-consumer-trusted-acceptance` 候補 | blocked | 実装しない。public evidence を private trusted artifact へ昇格しない |
| `onnx-windows-x64-manual.yml` | `rust-eval` 候補 | upstream-required | **Windows/DirectML provider route workflow を新規実装** |
| `jpapt-upstream-contract-diff.yml` | `candidate-routing-config-fetch` 候補 | upstream-required | **upstream contract diff route workflow を新規実装** |
| `cloud-config.yml` | なし | local-only | 本 repo 対象外 |
| `hf-model-pipeline-security-contracts.yml` | なし | local-only | 本 repo 対象外 |
| `jpapt-upstream-contract-diff-contracts.yml` | なし | local-only | 本 repo 対象外 |
| `jpapt-private-receipt.yml` | `jpapt.candidate-completed` 等 | callback-only | 親側に残す。本 repo は completion/ACK sender を維持 |

`upstream-required` と `blocked` を無理に dispatch 成功へ変換してはならない。HTTP 204 や router 受付だけを PASS としない。

## 4. 公開正本へ追加すべき workflow（実装スコープ）

### 4.1 `ghcr-public-verify`

`ghcr-package-provision.yml` の `verify-public` を代替する。

要件:

- `workflow_dispatch` を公開し、`repository-dispatch` router から `jpapt.workflow` で呼び出せること
- 入力は digest-pinned `image` と `require_public=true` に限定
- GHCR login を行わず、registry `/v2/` tags/token API を匿名で確認
- 出力に `anonymous_pull_namespace=true`、`credentials_used=false`、対象 digest、HTTP status を含める
- candidate build、HF Bucket mutation、private secret 使用を行わない

想定 dispatch:

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "ghcr-public-verify",
    "ref": "main",
    "inputs": {
      "image": "ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec",
      "require_public": "true"
    }
  }
}
```

関連: 親 [`jpapt-issues-160-verify-public-dispatch-bypass.md`](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-issues-160-verify-public-dispatch-bypass.md)

### 4.2 `fixture-generation-and-inspection`

要件:

- fixed source SHA、Bucket run、generation ID、upload-only reviewed plan、delete 禁止、receipt を contract 化
- HF Jobs は必要な場合のみ起動
- generation と inspection を別 identity で保存
- HF Jobs smoke 単体を fixture generation の代替とみなさない

### 4.3 Windows/DirectML provider route

要件:

- `onnx-windows-x64-manual.yml` 相当の source SHA、candidate、variant、provider、validation mode、Bucket evidence を受ける
- Windows runner の結果を external receipt として保存
- Linux HF Jobs smoke を Windows provider 成功と解釈しない

### 4.4 upstream contract diff route

要件:

- upstream authority の固定 SHA、直前 SHA、対象変更 commit、変更 file、契約差分を artifact として提示
- local repository への自動 merge、Bucket mutation、HF Jobs 起動、release publish を行わない
- `candidate-routing-config-fetch` だけでは full contract diff にならない点を明記

## 5. 関連親ドキュメントの要約

### 5.1 external-dispatch migration（正本一覧）

- 親は実行 workflow を増やさず、公開正本へ dispatch する
- 確認時点の inspected public SHA は `149d689dfbc9a52774064305836c0ff45f5b7e9b`。本ブランチ着手時の `main` は `5d4974fb8e10b04088a419e37545b1e5cedd900e`。moving `main` を黙って使わず、40 桁 SHA と差分を記録する
- `request_execution_id` は Gateway が発行。caller payload に含めない
- token、HF credential、private source 本文、音声、cache を dispatch payload に入れない

### 5.2 #134 canonical CTC upload procedure

- canonical CTC ONNX pair を source Bucket から `gawohok7/jpapt-v2.2-dev` へ移送し、immutable revision で provenance に結合する手順
- 固定 source run: `20260820-tdt-ctc-a03f760`、target immutable SHA: `8e884722a08d6d791fa83d28af3d34ed762ba14c`
- upload 成功だけで #134 complete としない。全 material asset inventory、candidate transfer mapping、routing enablement は別 gate
- GHCR Public 化・HF Jobs・issue close はこの手順から自動実行しない

本 repo 側の対応: [`parakeet-provenance-and-routing-responsibility.md`](./parakeet-provenance-and-routing-responsibility.md)、[`parakeet-provenance-remaining-work-and-parent-contract-20260820.md`](./parakeet-provenance-remaining-work-and-parent-contract-20260820.md)、PR #192 で merge 済み provenance contract

### 5.3 #154 public inspection bypass

- Private Actions billing 制限下で、public Gateway + HF Jobs Smoke から external/provider evidence を取得する runbook
- `event_type=jpapt.candidate-request`、`execute=false` で plan-only、`execute=true` で Gateway-owned execution identity による V2 dispatch
- 固定 candidate `candidate-000001`、digest-pinned `jpapt-candidate` image、`smoke/hf_jobs/linux-cpu`
- 取得できるのは public external evidence のみ。private trusted builder acceptance へ自動昇格しない

本 repo 側の対応: 既存 [`candidate-request-gateway.yml`](../.github/workflows/candidate-request-gateway.yml)、[`jpapt-issues-154-public-inspection-bypass.md`](./jpapt-issues-154-public-inspection-bypass.md)、[`scripts/ci/dispatch-public-inspection-bypass.sh`](../scripts/ci/dispatch-public-inspection-bypass.sh)

### 5.4 #160 verify-public dispatch bypass

- 公開正本 SHA `149d689...` 時点では `verify-public` workflow は存在しない
- 即時迂回: `jpapt.workflow` → `ghcr-audit` + caller 側 `ghcr-anonymous-pull-preflight.py`
- 公開 audit は GitHub token で GHCR login するため、匿名公開性の最終証拠ではない
- 真の remote verify には **`ghcr-public-verify` workflow の merge が先**

### 5.5 #160/#154/#134 resolution plan

- 対象ブランチ名（親側計画）: `feat/jpapt-issues-160-154-134-resolution`
- PR #192 merge 後の provenance contract（`revisions/provenance.json`、fingerprint binding、fail-closed routing）を現行境界とする
- RD-I160 / RD-I154 / RD-I134 の作業単位と close 条件を定義
- local fixture PASS を external acceptance へ昇格しない

## 6. 本 repository の現行 dispatch 基盤

外部 dispatch の transport と validation は次が正本である。

| コンポーネント | パス |
|---|---|
| Router workflow | [`.github/workflows/repository-dispatch.yml`](../.github/workflows/repository-dispatch.yml) |
| Rust resolver | `rust/crates/asr-contracts/src/bin/asr-workflow-dispatch.rs` |
| 汎用 workflow route | `event_type=jpapt.workflow` |
| Candidate Gateway | `event_type=jpapt.candidate-request` → [`candidate-request-gateway.yml`](../.github/workflows/candidate-request-gateway.yml) |
| Bucket bootstrap | `event_type=jpapt.bucket-bootstrap` → [`external-bucket-bootstrap.yml`](../.github/workflows/external-bucket-bootstrap.yml) |
| 説明 | [`repository-dispatch.md`](./repository-dispatch.md) |

新規 workflow を追加する場合の必須作業:

1. `.github/workflows/<name>.yml` に `workflow_dispatch` inputs を定義
2. `ghcr-contracts.yml` 等の Rust workflow-input contract test が通ること
3. `mise run actions-list` / `mise run actions-validate` で router 登録を確認
4. default branch merge 後にのみ `repository_dispatch` が有効（GitHub platform 制約）
5. receipt / summary artifact に token redaction と machine-readable identity を含める

## 7. Unit 0 gap 表（2026-08-20 照合）

着手 commit: `66b9ac4a37d72aeea7941691f8ba5cfff858dc1f`。`asr-workflow-dispatch validate` は全 workflow の `workflow_dispatch` 必須契約を満たすこと。

| 親 local workflow | 親 dispatch route | route 状態 | 本 repo 既存 partial | 本ブランチ実装 target | 親 issue |
|---|---|---|---|---|---|
| `ghcr-package-provision.yml` | `jpapt.workflow` → `ghcr-audit` | partial | [`ghcr-audit.yml`](../.github/workflows/ghcr-audit.yml)（認証付き） | **`ghcr-public-verify`** | #160 |
| `hf-model-bootstrap-package.yml` | `jpapt.bucket-bootstrap` | available | [`external-bucket-bootstrap.yml`](../.github/workflows/external-bucket-bootstrap.yml) | contract 確認のみ | — |
| `hf-model-pipeline.yml` | `jpapt.candidate-request` | retired | [`candidate-request-gateway.yml`](../.github/workflows/candidate-request-gateway.yml) | 新規不要 | #154 |
| `fixture-generation-and-inspection.yml` | `hf-jobs-smoke` 候補 | upstream-required | [`hf-jobs-smoke.yml`](../.github/workflows/hf-jobs-smoke.yml)（smoke dispatch のみ） | **`fixture-generation-and-inspection`** | — |
| `jpapt-private-dispatch.yml` | `jpapt.candidate-request` | available | Gateway + [`dispatch-public-inspection-bypass.sh`](../scripts/ci/dispatch-public-inspection-bypass.sh) | 新規不要 | #154 |
| `jpapt-package-artifact-verify.yml` | `private-consumer-trusted-acceptance` | blocked | [`private-consumer-trusted-acceptance.yml`](../.github/workflows/private-consumer-trusted-acceptance.yml) | **実装しない** | #154 |
| `onnx-windows-x64-manual.yml` | `rust-eval` 候補 | upstream-required | [`rust-eval.yml`](../.github/workflows/rust-eval.yml) `windows-directml` | **`windows-directml-provider-route`** | — |
| `jpapt-upstream-contract-diff.yml` | routing fetch 候補 | upstream-required | [`fetch-source-routing-config.sh`](../scripts/ci/fetch-source-routing-config.sh) のみ | **`upstream-contract-diff`** | #134 |

**available partial の blocker（実装対象外）**

- #154 live Gateway: `SOURCE_REPO_TOKEN` 未設定時は private source probe が 404
- #160 即時迂回: `ghcr-audit` は匿名公開証明にならない

## 8. 作業単位（recursive delivery）

### Unit 0: 正本固定と gap 分析

- 親 migration 表と本 repo の workflow 一覧を照合
- inspected SHA（着手時 `5d4974f`）上で `upstream-required` workflow の有無を確認
- 既存 partial route（Gateway、`ghcr-audit`、bucket bootstrap）の contract test 状態を記録

受入れ: gap 表、固定 SHA、既存/新規 workflow の対応表

### Unit 1: `ghcr-public-verify`

- workflow 実装、contract test、router 経由 dispatch 例、receipt schema
- 匿名 API のみ。`credentials_used=false` を artifact へ出力

受入れ: plan-only 相当の dry validation + reviewed remote dispatch で receipt 保存（merge 後）

### Unit 2: `fixture-generation-and-inspection`

- generation ID、Bucket run、inspection receipt の identity 分離
- delete 禁止、upload-only plan

受入れ: schema + contract test。HF Jobs 起動は reviewed execute のみ

### Unit 3: Windows/DirectML provider route

- Windows runner、DirectML provider、external receipt
- Linux smoke との混同禁止

受入れ: Windows runner 上での contract test と receipt

### Unit 4: upstream contract diff route

- fixed SHA diff artifact
- Bucket mutation / auto-merge なし

受入れ: artifact に changed files と contract delta

### Unit 5: 親 caller 連携確認

- 親 `jpapt-external-dispatch.py plan` が新 workflow alias を解決できること（親側 config 更新は別 PR）
- #154 plan/execute、#160 verify、#134 routing/provenance gate との境界を docs へ反映

## 11. 実装完了と dispatch 例（2026-08-20）

本ブランチで追加した upstream-required workflow と、`jpapt.workflow` 経由の dispatch 例。merge 前の branch では GitHub platform 制約により `repository_dispatch` は default branch 上でのみ有効。

| workflow alias | 用途 | evidence 境界 |
|---|---|---|
| `ghcr-public-verify` | #160 匿名 GHCR verify | `credentials_used=false` receipt。`ghcr-audit` 代替ではない |
| `upstream-contract-diff` | #134 contract delta | git diff のみ。Bucket mutation なし |
| `fixture-generation-and-inspection` | fixture generation plan/execute | generation_id / inspection_id 分離。HF Jobs は別 gate |
| `windows-directml-provider-route` | Windows DirectML external route | `linux_hf_jobs_smoke_equivalent=false` |

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "ghcr-public-verify",
    "ref": "main",
    "inputs": {
      "image": "ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec",
      "require_public": true
    }
  }
}
```

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "upstream-contract-diff",
    "ref": "main",
    "inputs": {
      "baseline_revision": "5d4974fb8e10b04088a419e37545b1e5cedd900e",
      "public_revision": "66b9ac4a37d72aeea7941691f8ba5cfff858dc1f",
      "source_repository": "largoyo/Premiere-AutoProcess-Plugin"
    }
  }
}
```

**NOT VERIFIED until merge / reviewed remote run**

- `repository_dispatch` router on default branch
- 親 `config/jpapt-external-dispatch.v1.json` 更新 → [`parent-repository-external-dispatch-config-handoff-20260820.md`](./parent-repository-external-dispatch-config-handoff-20260820.md)
- #154 Gateway plan/execute + completion/ACK live run
- private trusted package evidence

## 9. 非目標・禁止事項

- 親 repository `.github/workflows/` へ実行 workflow を追加しない（親 migration 方針）
- `upstream-required` workflow を未実装のまま dispatch 成功扱いしない
- public audit、local anonymous preflight、public HF Jobs receipt、private trusted artifact を同一証跡として扱わない
- dispatch payload / artifact / log へ token、credential、private source 本文、音声を出力しない
- #134 upload、#154 bypass、#160 verify を単独成功として issue close 条件へ自動昇格しない

## 10. 参照資料

### 親リポジトリ（dispatch 正本）

- [jpapt-github-actions-external-dispatch-migration.md](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-github-actions-external-dispatch-migration.md)
- [jpapt-issues-134-canonical-ctc-upload-procedure.md](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-issues-134-canonical-ctc-upload-procedure.md)
- [jpapt-issues-154-public-inspection-bypass.md](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-issues-154-public-inspection-bypass.md)
- [jpapt-issues-160-verify-public-dispatch-bypass.md](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-issues-160-verify-public-dispatch-bypass.md)
- [jpapt-issues-160-154-134-resolution-plan.md](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-issues-160-154-134-resolution-plan.md)

### 本 repository

- [`repository-dispatch.md`](./repository-dispatch.md)
- [`jpapt-issues-154-public-inspection-bypass.md`](./jpapt-issues-154-public-inspection-bypass.md)
- [`jpapt-issues-154-public-inspection-bypass-plan.md`](./jpapt-issues-154-public-inspection-bypass-plan.md)
- [`parent-repository-current-spec-handoff-20260820.md`](./parent-repository-current-spec-handoff-20260820.md)
- [`parakeet-provenance-and-routing-responsibility.md`](./parakeet-provenance-and-routing-responsibility.md)
