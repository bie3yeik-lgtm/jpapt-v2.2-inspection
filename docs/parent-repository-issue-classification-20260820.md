# 親リポジトリ issue / PR の現行仕様照合

作成日: 2026-08-20
対象: `largoyo/Premiere-AutoProcess-Plugin` から派生した JPAPT / Hugging Face / GitHub Actions 関連の issue と PR

## 1. 判定の基準

この文書では、親リポジトリの履歴をそのまま本リポジトリの仕様とはみなさない。現行の正本は次の順序で判定する。

1. `rust/crates/` の実装と Rust contract validator
2. `config/`、`contracts/`、`evaluation/schemas/` の source-controlled contract
3. `.github/workflows/` の実行構成
4. `docs/` の現行仕様
5. 親リポジトリの issue / PR は、移行履歴と外部証跡としてのみ参照

特に、親リポジトリ固有の private Actions、MCP connector、親側の GHCR Package Settings は、この公開 authority repository の CI完了条件へ直接移植しない。

## 2. 現行仕様への取り込み状況

### 取り込む内容

| 親 issue / PR | 現行仕様へ取り込む内容 | 現行の対応先 |
|---|---|---|
| #134 | Parakeet の repository-level metadata だけで provenance 完了とみなさない。exact revision、material asset、origin、license、transformation を分離して確認する。 | `config/` の target/model policy、revision bundle、[docs/contracts.md](contracts.md)、[docs/workflows.md](workflows.md) |
| #154 | candidate bytes、artifact SHA-256、run identity、candidate bundle SHA、image/package identity を分離し、accepted run と promotion の前に再検証する。 | `evaluation/schemas/`、`rust/crates/asr-contracts`、[docs/evaluation.md](evaluation.md)、[docs/ghcr-ci.md](ghcr-ci.md) |
| #160 | mutable tag と digest を同一視しない。provider/package/readiness と実行証明を分離する。匿名 pull の親リポジトリ固有手順は一般原則としてのみ保持する。 | [docs/providers.md](providers.md)、[docs/ghcr-ci.md](ghcr-ci.md)、[docs/candidate-protocol-e2e.md](candidate-protocol-e2e.md) |
| #133 | legacy evaluator を第二の authority として復活させず、Rust authority、portable receiver、completion/ACK/lifecycle を分離する。 | [README.md](../README.md)、[docs/candidate-protocol-runtime-boundary.md](candidate-protocol-runtime-boundary.md)、[docs/candidate-completion-protocol.md](candidate-completion-protocol.md) |
| PR #184 | status/handoff は source-controlled authority、external proof、operational blocker を分離して記録する。 | 本文書、[docs/README.md](README.md) |
| PR #185 | paid compute は目的・identity・timeout・cost を先に固定し、connector failure で再送しない。 | 現行 docs の安全原則として採用。ただし `$2.00` の親リポジトリ固有上限は採用しない。 |

### 親リポジトリ固有として保持する内容

| 親 issue / PR | 判定 | 理由 |
|---|---|---|
| #127 | 親リポジトリ固有 | `largoyo/Premiere-AutoProcess-Plugin` の private hosted Actions が checkout 前、`steps=null` で停止した事象。本リポジトリの public authority CIの失敗とは同一視しない。 |
| #130 | 外部 connector 固有 | HF Jobs MCP の structured-output decoder が historical record を返せない問題。本リポジトリの公式 `hf` CLI、Bucket contract、Rust resolver の仕様ではない。 |
| PR #184 | 履歴資料 | 親 private `main` の SHA、親側 package/GHCR 状態、親側 blocker を含む。現行 authority の revision や本リポジトリの CI成功証明には使わない。 |
| PR #185 | 履歴資料 | `$2.00` cumulative HF Jobs hard cap は親タスクへの運用引き継ぎ条件。本リポジトリの現行 contract ではない。paid compute を使う場合は別途、明示的な承認・費用・timeout・evidence を定義する。 |

## 3. 各 issue の現行判定

### #127 — CI: GitHub Actions jobs fail before first step

判定: **過去／親リポジトリ固有**。

親リポジトリの private Actions 実行基盤、billing、runner entitlement、organization policy の調査課題であり、本リポジトリの Rust/Python/ONNX contract の不具合を示す証拠ではない。`steps=null` は source test failure として再利用しない。

現行リポジトリでの対応は、既存の `.github/workflows/` と local contract checks を正本とする。親 repository の private runner を本リポジトリの CI prerequisite にしない。

### #130 — HF Jobs MCP structured-output schema mismatch

判定: **過去／外部 connector 固有**。

MCP が response を repository code へ渡す前に失敗するため、repository-local normalizer では解決できない。本リポジトリは HF transport boundary として公式 CLI/API、Rust contract、明示的な Bucket identity を使用する。MCP historical-job decoder を CI authority にしない。

### #133 — Migrate legacy hf-model-pipeline to jpapt authority path

判定: **吸収済み／umbrella issue は obsolete**。

legacy evaluator の退役、Rust authority、request/receipt/rejection/ACK/lifecycle、candidate/evaluation/promotion 境界は現行仕様へ吸収済みである。残る external E2E は、本リポジトリでは Issue #70/#71 として管理される。本 issue の親リポジトリ migration umbrella を現行実装計画へ残さない。

### #134 — Verify Parakeet dev repo provenance before candidate routing

判定: **現行仕様へ取り込む／未完了**。

この内容は、Parakeet route の source-controlled revision、material asset、tokenizer/config、変換履歴、license/attribution を exact identity で確認する必要性として現行仕様に一致する。ただし repository-level `cc-by-4.0` metadata だけでは完了としない。

現行の config/revision fetch が `config-000003` の旧 `config_revision` pointerと欠落した `runtime.json` で停止したことも、この fail-closed 方針と整合する。remote Bucket を推測で補正しない。

### #154 — Bind HF package evidence to trusted GitHub artifact/run identity

判定: **一部取り込み／親側実証は未完了**。

candidate content digest、artifact archive digest、workflow run/attempt、image digest、promotion acceptance を分離する設計は現行仕様へ取り込む。一方、親 private repository からの real package artifact、private Actions run、GHCR package evidence は本リポジトリの local/static CIでは証明できない。

本リポジトリでの完了条件は accepted `full` run、candidate bundle SHA、run-context、metrics、promotion validation とする。親 repository の artifact proof をこれらの代替にしない。

### #160 — Guarantee HF Jobs can pull package images produced by private GHCR workflow

判定: **一部取り込み／親側運用課題は未完了**。

digest-pinned identity、registry readiness、credential を request/evidenceへ埋め込まないことは現行仕様と一致する。しかし、親 private repository の GHCR Public visibility、`verify-public`、親 package workflow の実 artifact は親側 operator / infrastructure の責務であり、本リポジトリの現行 CI完了条件ではない。

現行 repository では provider registration、session creation、inference、execution proof、node assignment proof を分離する。同じ原則を package/registryにも適用するが、未確認の親側 artifactを成功扱いしない。

## 4. PR #184 / #185 の扱い

### PR #184

親リポジトリの migration status document は、2026-08-20 時点の親 private `main`、親側 accepted JPAPT revision、GHCR/package blocker をまとめた履歴資料である。構造化された status/handoff の形式は参考にするが、記載された親 `main` SHAや accepted revisionをこの repository の現行 HEAD・正本として扱わない。

### PR #185

HF Jobs の `$2.00` cumulative hard cap、live pricing、timeout、worst-case accounting、no-resubmit は、親側の Codex handoff として有用な安全原則である。ただし本 repository の仕様へ固定値 `$2.00` を導入しない。新しい paid compute が必要になった場合は、別途明示承認を得て、対象、費用上限、timeout、secret boundary、永続化先、evidence を記録する。

## 5. Issue close 方針

今回、現行仕様と責務が明確に異なる以下を親リポジトリで close する。

- #127: 親 private Actions infrastructure の過去 blocker
- #130: 親側 MCP connector decoder の過去 blocker
- #133: 現行 JPAPT authority/lifecycle へ吸収済みの umbrella migration

以下は未完了の実証または現行 Parakeet provenance と直接関係するため close しない。

- #134: Parakeet material provenance 未完了
- #154: real package artifact/run evidence 未完了
- #160: GHCR readiness と real package proof 未完了

close は「source code が完成した」という意味ではなく、「親 issue を本 repository の現行仕様の未完了項目として維持しない」という意味で行う。#134/#154/#160 の外部証跡が後日得られた場合は、親 issueではなく本 repository の current contract / evidence schema に反映する。

## 6. 現行の再開順序

1. HF Bucket の現行 pointer と revision bundle を source-controlled contract に合わせる。旧 field 名や欠落ファイルを推測で補正しない。
2. Parakeet provenance を exact revision / asset / transformation 単位で完成させる。
3. candidate contract と Rust CTC evaluator の parity/evaluation evidence を取得する。
4. external callback fixture（Issue #70）と private lifecycle storage proof（Issue #71）を、親 repository の private Actions証跡とは分離して実施する。
5. accepted `full` run、SHA-256、promotion gate を満たした後にのみ release/promotion を扱う。

## 7. 参照元

- [親 issue #127](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/127)
- [親 issue #130](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/130)
- [親 issue #133](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/133)
- [親 issue #134](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/134)
- [親 issue #154](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/154)
- [親 issue #160](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/160)
- [親 PR #184](https://github.com/largoyo/Premiere-AutoProcess-Plugin/pull/184)
- [親 PR #185](https://github.com/largoyo/Premiere-AutoProcess-Plugin/pull/185)
