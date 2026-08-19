# 親リポジトリ向け現行仕様引き継ぎ

実装受領入口: [`recursive-delivery-entry-20260820.md`](./recursive-delivery-entry-20260820.md) / [`parakeet-provenance-and-routing-responsibility.md`](./parakeet-provenance-and-routing-responsibility.md)

作成日: 2026-08-20
送付先: `largoyo/Premiere-AutoProcess-Plugin`
正本: `largoyo/Premiere-AutoProcess-Plugin` の親 repository ではなく、`jpapt-v2.2-inspection` の現行 `main`、Rust contract、source-controlled config/schema、workflow

## 1. この文書の目的

親リポジトリで発生した #154 / #160 を含む JPAPT・HF Bucket・GHCR・GitHub Actions 関連の課題について、現行仕様での扱いを明確にする。

親リポジトリの private Actions 実行状態や個別の package artifact を、本 repository の評価成功・promotion成功・external E2E成功の代替証拠にはしない。親リポジトリは、以下に示す現行 contract に適合する request/input/evidence を生成する consumer として扱う。

## 2. 現行 authority と責務境界

authority の優先順位は次のとおり。

1. Rust implementation / validator (`rust/crates/`)
2. source-controlled contract (`config/`, `contracts/`, `evaluation/schemas/`)
3. GitHub Actions workflow YAML
4. `docs/`
5. 親リポジトリの issue / PR は履歴・外部証跡

主な責務分担:

| 領域 | 現行 authority | 親リポジトリが行うこと |
|---|---|---|
| target / Bucket / Model Repo routing | `asr-hf`、`config/hf-targets/`、`config/models/`、`config/asr-catalog.json` | target ID を指定し、導出値を再定義しない |
| config revision | Rust config resolver、HF Bucket `config/current.json` と immutable version | `HF_CONFIG_VERSION` の明示選択を使う場合は version を固定する |
| candidate identity | Bucket canonical candidate layout、inspection contract、bundle SHA-256 | candidate path/metadataを手作業で上書きしない |
| evaluation | Python ONNX boundary + Rust CTC evaluator | `run-context` と resolved manifest を変更せず使う |
| execution environment | GHCR digest-pinned reference/export image | tagをrun identityにしない |
| run / benchmark / capsule | Rust validator、`results/<run>`、HF Bucket | `run-context`、metrics、capsuleを一組で保存する |
| promotion | accepted `full` run、candidate bundle SHA、Rust promotion gate | accepted条件を親側で緩めない |
| completion / ACK / lifecycle | Rust protocol authority + portable external receiver | `request_id` と `request_execution_id` を混同しない |
| external E2E | dedicated receiver fixture、Issue #70/#71 | 親 private Actionsの成功を外部E2E証明とみなさない |

## 3. #154 の現行仕様への対応

親 issue: [#154 Bind HF package evidence to trusted GitHub artifact/run identity](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/154)

### 3.1 取り込むべき原則

親 issue の次の原則は現行仕様に適合する。

- candidate bytes と package/reference environment を別 identity とする
- artifact SHA-256、candidate bundle SHA、run ID、experiment ID を別々に保持する
- tagではなく immutable digest/revision を保存する
- run開始時に `run-context.json` へ model、candidate、variant、provider、environment、evaluation、config、dataset、experiment を freeze する
- validation後の candidate/config/provider/suite 差し替えを禁止する
- promotion前に candidate を再fetchし、actual artifactから runtime contract と bundle identity を再検証する
- `acceptance.passed == true`、`evaluation_id == full`、candidate ID/SHA一致を promotion gate とする

### 3.2 現行 repository での証拠形式

標準評価結果:

```text
results/<run>/
├── run-context.json
├── samples.jsonl
├── metrics.json
└── run.parquet
```

run-context では、GHCR reference/export environment を次のように digestで固定する。

```json
{
  "ghcr": {
    "image": "ghcr.io/<namespace>/<package>",
    "digest": "sha256:...",
    "reference": "ghcr.io/<namespace>/<package>@sha256:...",
    "role": "reference-export"
  }
}
```

この image は candidate ONNX artifact ではない。candidate は HF Bucket、reference/export environment は GHCR、run/capsule は HF Bucket runs に保存する。

### 3.3 親リポジトリ側でやること

親リポジトリが package evidence を作る場合でも、次を本 repository の evidence と混ぜない。

1. 親 workflow の source repository、head SHA、workflow run ID、run attempt を保存する。
2. candidate content digest、package image digest、GHCR reference environment digestを別フィールドで保存する。
3. 親側 artifact を JPAPT requestへ渡す場合は、現行 public request schemaを拡張せず、既存の digest-pinned `hf_jobs_image` / execution identity境界に合わせる。
4. 本 repository の Rust validator が受理できる `run-context`、metrics、candidate bundle SHAを生成する。
5. real package artifact がない場合は `planned` / `dry_run` / `inconclusive` とし、成功扱いしない。

親 private Actions が checkout 前に `steps=null` で停止する #127 の状態では、#154 の real producer artifact evidence は成立しない。source contract が正しいことと、親 workflow が実行されたことを分離する。

## 4. #160 の現行仕様への対応

親 issue: [#160 Guarantee HF Jobs can pull package images produced by private GHCR workflow](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/160)

### 4.1 現行の GHCR model

本 repository では GHCR image を candidate そのものではなく、reference/export/evaluation environment として扱う。

```text
Dockerfile labels
  -> source-controlled HF target routing
  -> GHCR build/publish
  -> immutable RepoDigest freeze
  -> digest-pinned evaluation
  -> HF Bucket run/benchmark evidence
```

`latest` や git SHA tag は実験 identity ではない。評価時に取得した `RepoDigest` を `metadata.ghcr.digest` として保存し、実行対象は次の形に固定する。

```text
ghcr.io/<namespace>/<package>@sha256:<digest>
```

### 4.2 認証と公開性の扱い

canonical GHCR workflow は次の境界を使う。

- read: `contents: read` + `packages: read`
- publish: job-local `packages: write`、attestation権限
- authentication: ephemeral `github.token`
- PAT fallback: なし
- HF token、GHCR token、candidate ID、mutable revisionを Docker layerへ埋め込まない

親 issue の「private GHCRをPublic化しないとHF Jobsがpullできない」という運用課題は、親 repository の registry/package provisioning に固有である。現行 repository では、まず digest freeze、label validation、GHCR audit、digest-pinned evaluation の順で確認する。Public visibilityを変更したことだけでは、package build、image identity、evaluation execution、provider proofの成功を意味しない。

### 4.3 現行の検証段階

GHCR と評価の証拠は次を分離する。

1. target/Dockerfile label mapping
2. package build / environment import smoke
3. image publish と returned digest validation
4. attestation
5. registry audit
6. digest-pinned evaluation session
7. run validation と HF Bucket upload
8. provider execution proof / node assignment proof

Linux GHCR CPU evaluationは Windows DirectML / macOS CoreML の代替証拠ではない。DirectML/CoreMLは native provider laneで別途確認する。

親 repository の `verify-public` が成功しても、上記の全段階が証明されない限り #160 の完了とは扱わない。

## 5. 親リポジトリから現行 repositoryへ渡す最小情報

親側から request / package / evidence を渡す場合、最低限次を machine-readable に保持する。

```text
source_repository
source_revision
workflow_path
workflow_run_id
workflow_run_attempt
candidate_id
candidate_content_digest
candidate_bundle_sha256
model_id / hf_target_id
runtime_variant / decoder
config_version
datasets_lock_sha256
environment_id
ghcr_image
ghcr_repo_digest
provider_id
evaluation_id
experiment_id
run_id
```

不明な値は推測せず、nullable/未完了状態として記録する。mutable URI、tagのみ、repository-level license metadataのみでは provenance 完了としない。

## 6. 親側 issue の現在の扱い

| issue | 現行との関係 | 引き継ぎ判断 |
|---|---|---|
| #127 | 親 private Actions infrastructure | 本 repository の CI blockerにしない。親側でのみ解決する。 |
| #130 | HF Jobs MCP decoder | 現行 HF CLI/Rust authorityに取り込まない。paid Job再送の根拠にしない。 |
| #133 | legacy migration umbrella | 現行 authority/lifecycleへ吸収済み。close済み。 |
| #134 | Parakeet material provenance | 現行 routeへ直接関係。exact revision/asset inventoryが完了するまで blocked。 |
| #154 | real package/artifact provenance | 原則は取り込む。親側 real artifactは別証跡として保持し、現行 run/promotion contractへ変換する。 |
| #160 | GHCR distribution/readiness | digest identity と段階的 proofを取り込む。親側 Public/verify-public 状態だけで完了扱いしない。 |

## 7. 次の実行手順

### 親 repository側

1. #154/#160 の親側 artifact・registry証拠を、mutable tagではなくdigestで再整理する。
2. private Actions `steps=null` が解消していない場合、real package artifactを成功扱いしない。
3. package evidenceが本当に存在する場合、source/run/attempt/archive digestを保存する。
4. requestへ渡す際は、candidate、environment、run、providerを別 identityにする。
5. external completion/ACKは `request_id` と `request_execution_id` を保持して送信する。

### 本 repository側

1. HF Bucket `config/current.json` と immutable revision bundleを現行 schemaで取得する。
2. Parakeet candidate provenanceを exact revision/asset単位で確定する。
3. candidate contractを生成し、Rust CTC evaluatorで `smoke` → `parity` → `full` を実施する。
4. `run-context`、metrics、capsule、provider evidenceをRust validatorで検証する。
5. accepted `full` runだけをpromotion対象にする。
6. external receiver fixtureとprivate lifecycle storage proofをIssue #70/#71の境界で検証する。

## 8. 完了判定

#154/#160 に関する親側情報を現行仕様へ反映したと判断できるのは、次をすべて満たした場合だけである。

```text
candidate content identity is immutable
candidate bundle SHA is validated
config/dataset/revision identities are frozen
GHCR environment is digest-pinned
workflow run/attempt provenance is concrete
run-context/metrics/capsule validate together
accepted full evaluation exists
promotion gate passes
external completion/ACK/lifecycle identity binding passes when required
```

Public visibility、MCPが返したJob ID、repository-level license、GitHub APIのdispatch acceptedだけでは、上記完了条件を満たさない。

## 9. 参照資料

- [docs/README.md](README.md)
- [docs/architecture.md](architecture.md)
- [docs/ghcr-ci.md](ghcr-ci.md)
- [docs/evaluation.md](evaluation.md)
- [docs/candidate-completion-protocol.md](candidate-completion-protocol.md)
- [docs/candidate-protocol-e2e.md](candidate-protocol-e2e.md)
- [parent issue #154](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/154)
- [parent issue #160](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/160)
- [parent PR #184](https://github.com/largoyo/Premiere-AutoProcess-Plugin/pull/184)
- [parent PR #185](https://github.com/largoyo/Premiere-AutoProcess-Plugin/pull/185)
