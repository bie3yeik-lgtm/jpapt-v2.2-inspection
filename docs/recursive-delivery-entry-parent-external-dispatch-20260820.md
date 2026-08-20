# Recursive Delivery Entry: Parent External Dispatch Workflows

作成日: 2026-08-20
対象ブランチ: `feat/parent-external-dispatch-workflows`
親リポジトリ: `largoyo/Premiere-AutoProcess-Plugin`
正本ドキュメント: [`parent-external-dispatch-workflows-20260820.md`](./parent-external-dispatch-workflows-20260820.md)

## 着手目的

親リポジトリは Private Actions Billing に依存せず、JPAPT 実行を公開正本
`bie3yeik-lgtm/jpapt-v2.2-inspection` へ `repository_dispatch` する。本ブランチは、
親 migration 文書で `upstream-required` とされた公開 workflow を実装し、#134 / #154 / #160
に関連する dispatch 経路を router から解決可能にする。

## 最初の作業単位

Unit 0 として、着手時 `main` SHA `5d4974fb8e10b04088a419e37545b1e5cedd900e` 上の workflow
一覧と親 migration 表を照合し、次の 4 workflow を実装 backlog として固定する。

1. `ghcr-public-verify`
2. `fixture-generation-and-inspection`
3. Windows/DirectML provider route
4. upstream contract diff route

詳細要件・issue 対応・禁止事項は正本ドキュメントを参照する。

## 検証境界

### Unit 0（2026-08-20）

```text
gap table in parent-external-dispatch-workflows-20260820.md: PASS
asr-workflow-dispatch validate (after workflow_dispatch fix): PASS
upstream-required workflow implementation: IN PROGRESS
repository_dispatch on default branch: BLOCKED until merge
parent caller config update: OUT OF SCOPE for this repo
remote dispatch / HF Jobs / completion: NOT RUN
```

| Unit | 状態 | evidence |
|---|---|---|
| 0 | PASS | gap 表、validate |
| 1 | pending | `ghcr-public-verify` |
| 4 | pending | `upstream-contract-diff` |
| 2 | pending | `fixture-generation-and-inspection` |
| 3 | pending | `windows-directml-provider-route` |
| 5 | pending | handoff docs |
