# 親リポジトリ external-dispatch 設定更新 handoff

作成日: 2026-08-20
送付先: `largoyo/Premiere-AutoProcess-Plugin`
前提: 公開正本 [`bie3yeik-lgtm/jpapt-v2.2-inspection`](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection) の PR（`feat/parent-external-dispatch-workflows`）を `main` へ merge 済み
関連: [`parent-external-dispatch-workflows-20260820.md`](./parent-external-dispatch-workflows-20260820.md)

## 1. この文書の目的

公開正本側で 4 つの upstream-required workflow を実装した後、**親リポジトリ側で行う作業**を一箇所にまとめる。特に、次のステップ 2 に相当する。

1. （公開正本）PR を `main` へ merge する
2. **（親リポジトリ）`config/jpapt-external-dispatch.v1.json` と caller/docs を新 alias へ更新する** ← 本 handoff の主題
3. reviewed remote dispatch で receipt / artifact を保存する

親リポジトリは **新しい実行用 GitHub Actions workflow を追加しない**。route table と caller dispatcher の更新、migration 文書の status 更新、plan/dispatch 検証のみを行う。

## 2. 前提条件（merge 前に着手しない）

| 条件 | 確認方法 |
|---|---|
| 公開正本 PR が merge 済み | `bie3yeik-lgtm/jpapt-v2.2-inspection` の default branch に 4 workflow が存在 |
| merge commit SHA を記録 | 40 桁 lowercase SHA を migration 文書・config・work history へ固定 |
| `repository_dispatch` router が default branch 上で有効 | GitHub platform 制約: merge 前の branch dispatch は不可 |
| caller token が public repo へ dispatch 可能 | `PUBLIC_DISPATCH_TOKEN` 等。値はログ・payload・commit へ出力しない |

merge 後に固定する公開正本 SHA は、merge commit 自体を正本とする。moving `main` を黙って `ref: main` だけで使わない。

## 3. 親リポジトリで更新するファイル

| ファイル | 作業 |
|---|---|
| `TelopFlow_Feature/TF-v1-onnx-implements/config/jpapt-external-dispatch.v1.json` | route table を正本。4 alias を **available** へ更新 |
| `TelopFlow_Feature/TF-v1-onnx-implements/scripts/jpapt-external-dispatch.py` | 新 route の `plan` / `dispatch` が通ることを確認。必要なら alias 解決のみ最小修正 |
| `TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-github-actions-external-dispatch-migration.md` | workflow 別表の status を更新。inspected public SHA を merge SHA へ更新 |
| `TelopFlow_Feature/docs/work_history/` | 目的・変更ファイル・plan/dispatch 結果・未検証項目を記録 |

**更新しないもの**

- `.github/workflows/` への新規実行 workflow 追加
- `blocked` route（`jpapt-package-artifact-verify.yml` → private trusted acceptance）の成功扱い
- `local-only` route の public dispatch 化

## 4. route table 更新対象

親 migration 表と公開正本実装の対応。config 上では **local workflow 名 → public dispatch route** を更新する。

| 親 local workflow | 旧 status | 新 public alias | 新 status | 親 issue |
|---|---|---|---|---|
| `ghcr-package-provision.yml` (`verify-public`) | partial (`ghcr-audit`) | `ghcr-public-verify` | **available** | #160 |
| `jpapt-upstream-contract-diff.yml` | upstream-required (partial) | `upstream-contract-diff` | **available** | #134 |
| `fixture-generation-and-inspection.yml` | upstream-required | `fixture-generation-and-inspection` | **available** (plan-first) | — |
| `onnx-windows-x64-manual.yml` | upstream-required (`rust-eval` partial) | `windows-directml-provider-route` | **available** (plan-first) | — |

**変更しない route（参考）**

| 親 local workflow | route | status |
|---|---|---|
| `jpapt-private-dispatch.yml` | `jpapt.candidate-request` → Gateway | available（既存） |
| `hf-model-bootstrap-package.yml` | `jpapt.bucket-bootstrap` | available（既存） |
| `jpapt-package-artifact-verify.yml` | private-consumer-trusted-acceptance | **blocked** |
| `hf-model-pipeline.yml` | Gateway | retired |

## 5. `jpapt-external-dispatch.v1.json` 更新方針

config の exact schema は親 repo 正本に従う。公開正本 merge 後、各 route エントリに最低限含める項目:

| フィールド | 内容 |
|---|---|
| `local_workflow` | 親側 YAML 名（例: `ghcr-package-provision.yml`） |
| `status` | `available` / `blocked` / `local-only` |
| `event_type` | 多くは `jpapt.workflow`。Gateway 系は `jpapt.candidate-request` |
| `public_repository` | `bie3yeik-lgtm/jpapt-v2.2-inspection` |
| `public_workflow` | 下表 alias |
| `public_ref` | merge 後固定 SHA（初回 merge commit） |
| `requires_reviewed_execute` | plan/execute 分離 workflow は `true` |
| `evidence_artifact` | receipt/report ファイル名（運用メモ） |

### 5.1 `ghcr-public-verify`（#160）

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "ghcr-public-verify",
    "ref": "<merge-sha>",
    "inputs": {
      "image": "ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec",
      "require_public": true
    }
  }
}
```

受入れ: public workflow artifact の `credentials_used=false`、`anonymous_pull_namespace=true`、digest 一致。`ghcr-audit` や local `ghcr-anonymous-pull-preflight.py` だけでは #160 完了としない。

### 5.2 `upstream-contract-diff`（#134）

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "upstream-contract-diff",
    "ref": "<merge-sha>",
    "inputs": {
      "baseline_revision": "<previous-public-main-sha>",
      "public_revision": "<merge-sha>",
      "source_repository": "largoyo/Premiere-AutoProcess-Plugin"
    }
  }
}
```

受入れ: `.ci/upstream-contract-diff/report.json` に `contract_changed_files` と両 SHA。Bucket mutation なし。

### 5.3 `fixture-generation-and-inspection`

plan-only（必須先行）:

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "fixture-generation-and-inspection",
    "ref": "<merge-sha>",
    "inputs": {
      "source_revision": "<fixed-parent-or-public-sha>",
      "hf_bucket": "gawohok7/premiere-autoprocess-plugin-bucket",
      "generation_id": "gen-<stable-id>",
      "dry_run": true,
      "execute": false
    }
  }
}
```

reviewed execute（`confirm_execute=true` 必須）:

```json
{
  "inputs": {
    "source_revision": "<fixed-sha>",
    "hf_bucket": "gawohok7/premiere-autoprocess-plugin-bucket",
    "generation_id": "gen-<stable-id>",
    "dry_run": false,
    "execute": true,
    "confirm_execute": true
  }
}
```

受入れ: `generation_id` と `inspection_id` が receipt 上で分離。HF Jobs smoke 単体を fixture generation 完了とみなさない。

### 5.4 `windows-directml-provider-route`

plan-only:

```json
{
  "event_type": "jpapt.workflow",
  "client_payload": {
    "workflow": "windows-directml-provider-route",
    "ref": "<merge-sha>",
    "inputs": {
      "source_repository": "largoyo/Premiere-AutoProcess-Plugin",
      "source_revision": "<fixed-sha>",
      "hf_bucket": "gawohok7/premiere-autoprocess-plugin-bucket",
      "candidate_id": "candidate-000001",
      "validation_mode": "smoke",
      "dry_run": true,
      "execute": false
    }
  }
}
```

受入れ: receipt の `linux_hf_jobs_smoke_equivalent=false`、`provider_id=directml`、`runner_os=windows`。

## 6. 推奨作業順序（親 repo PR）

```text
1. 公開正本 merge SHA を取得し、migration 文書の inspected public SHA を更新
2. jpapt-external-dispatch.v1.json に 4 route を available として追加/更新
3. python3 scripts/jpapt-external-dispatch.py list で route 解決を確認
4. 各 route で plan-only（--print または dry_run/execute=false）を実行
5. migration 表の upstream-required → available を更新
6. work_history に plan 結果・artifact 名・未検証項目を記録
7. reviewed execute dispatch は別承認後（HF compute / Windows runner 発生）
```

## 7. 検証コマンド（親 repo 作業ディレクトリ）

```bash
# route 一覧
python3 TelopFlow_Feature/TF-v1-onnx-implements/scripts/jpapt-external-dispatch.py list

# plan-only（token 不要）
python3 TelopFlow_Feature/TF-v1-onnx-implements/scripts/jpapt-external-dispatch.py plan \
  --workflow ghcr-package-provision.yml \
  --payload-json '{"image":"ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec","require_public":true}'

# reviewed dispatch（token は環境から注入）
GH_TOKEN="$PUBLIC_DISPATCH_TOKEN" python3 TelopFlow_Feature/TF-v1-onnx-implements/scripts/jpapt-external-dispatch.py dispatch \
  --workflow ghcr-package-provision.yml \
  --payload-json '{"image":"ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec","require_public":true}'
```

HTTP 204 は受付のみ。公開 repo の workflow run URL と artifact/receipt を保存する。

## 8. 受入れ条件（親 repo PR）

| 項目 | 必須 |
|---|---|
| config に 4 alias が `available` | yes |
| migration 表と config status が一致 | yes |
| inspected public SHA が merge SHA で固定 | yes |
| plan-only が全 route で成功 | yes |
| token が commit/log/payload に含まれない | yes |
| blocked route を available へ昇格していない | yes |
| issue #134/#154/#160 を close していない | yes（config 更新だけでは close 不可） |

## 9. 公開正本側参照（merge 後に確認）

| alias | workflow | contracts |
|---|---|---|
| `ghcr-public-verify` | [`.github/workflows/ghcr-public-verify.yml`](../.github/workflows/ghcr-public-verify.yml) | `ghcr-public-verify-contracts.yml` |
| `upstream-contract-diff` | [`.github/workflows/upstream-contract-diff.yml`](../.github/workflows/upstream-contract-diff.yml) | `upstream-contract-diff-contracts.yml` |
| `fixture-generation-and-inspection` | [`.github/workflows/fixture-generation-and-inspection.yml`](../.github/workflows/fixture-generation-and-inspection.yml) | `fixture-generation-and-inspection-contracts.yml` |
| `windows-directml-provider-route` | [`.github/workflows/windows-directml-provider-route.yml`](../.github/workflows/windows-directml-provider-route.yml) | `windows-directml-provider-route-contracts.yml` |

dispatch 正本: [`repository-dispatch.md`](./repository-dispatch.md)

## 10. 関連 issue の扱い（close しない）

| issue | 親 repo config 更新で解消できる範囲 | まだ必要な作業 |
|---|---|---|
| #160 | `ghcr-public-verify` route 利用可能 | remote receipt、匿名 digest 実証、実 package 証跡 |
| #134 | `upstream-contract-diff` route 利用可能 | material inventory、provenance complete、routing enablement |
| #154 | 既存 Gateway route（変更なし） | live plan/execute、completion/ACK、private trusted artifact は別 |

## 11. 参照

- [親 jpapt-github-actions-external-dispatch-migration.md](https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/TelopFlow_Feature/TF-v1-onnx-implements/docs/jpapt-github-actions-external-dispatch-migration.md)
- [`parent-external-dispatch-workflows-20260820.md`](./parent-external-dispatch-workflows-20260820.md)
- [`recursive-delivery-entry-parent-external-dispatch-20260820.md`](./recursive-delivery-entry-parent-external-dispatch-20260820.md)
