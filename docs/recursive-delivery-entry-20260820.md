# Recursive Delivery Entry: Parakeet provenance

作成日: 2026-08-20
対象: `nvidia/parakeet-tdt_ctc-0.6b-ja` / `parakeet-tdt-ctc-v1`
関連: 親リポジトリ issue #134

## Objective

親リポジトリから受領する asset-level provenance を、現行 Rust-first contractへ取り込み、revision bundle、executable routing、run-context、capsule、promotionへ同一 fingerprintで結び付ける。

## Scope

対象は次のとおり。

- 独立 `provenance.json` のschemaとstrict validation
- provenance manifestのcanonical fingerprint
- revision bundleへのrequired document統合
- incomplete provenance時のcanonical execution gate
- run-context / capsule / promotionへのfingerprint binding
- 親リポジトリへ渡すinput contractと責務分離資料

対象外:

- 親リポジトリの実装、issue、PR、Actions、GHCR、MCPの変更
- private model/development assetの推測または取得
- HF Bucket remote objectの変更
- model export、ONNX生成、NeMo実行
- commit、push、release、promotion実行

## Frozen design decisions

- `provenance.json` は `reference.json` と分離する。
- `reference.json` はrepo/revision identity、`provenance.json` はasset origin/license/transformation/candidate transferを担当する。
- `status=complete` と `automation_consumption=true` は別条件とする。
- provenance未完了またはrouting enablement未承認の場合、canonical candidate fetch/evaluation/promotionを停止する。
- metadata-only target resolution、schema test、incomplete diagnosticは許可する。
- legacy revision bundleは自動補正せず、required `provenance.json`を満たさない場合はfail-closedとする。

## Dependency-ordered units

```text
Unit 0 entry / scope freeze
  -> Unit 1 schema / fixtures
  -> Unit 2 Rust validator / fingerprint
  -> Unit 3 revision bundle / run-context integration
  -> Unit 4 executable routing gate
  -> Unit 5 capsule / promotion / parent handoff binding
```

各unitは Orient → Define → Prove → Implement → Verify → Accept の順で処理する。失敗したunitを隠したfallbackで次へ進めない。

## Acceptance evidence

最低限、次を保存・報告する。

- valid incomplete/complete fixtureのschema検証
- invalid fixtureのfail証拠
- Rust validator unit/contract test
- provenance fingerprintのdeterminism
- revision bundle SHAへのprovenance反映
- incomplete provenanceのrouting negative test
- run-context/capsule/promotion fingerprint一致・不一致テスト
- 親側payload未提供時のblocked判定

## Current blockers and evidence boundary

親側から次が未提供である間、実運用のParakeet routeはcompleteにならない。

- exact upstream revision
- immutable development-repository snapshot/revision
- material asset inventory
- asset-level origin/license/attribution
- transformation chain
- candidate transfer mapping

schema/validatorのstatic、unit、local integration evidenceは取得できるが、private asset provenance complete、HF external proof、named platform runtime proofとは別の証拠レベルとして扱う。

## Rollback and external-action boundary

- 既存candidate/run artifactは書き換えない。
- 新規contractは未完了fixtureと明示的なgateで導入する。
- 生成物、cache、`.ci/`、`target/`、large model/audio artifactは追跡しない。
- commit、push、親リポジトリ操作、HF Bucket mutationは明示承認なしに実施しない。

## Implementation evidence (2026-08-20 continuation)

- Unit 1: schema、complete/incomplete/invalid fixture、Python schema testを追加済み。
- Unit 2: Rust strict validator、canonical sorted-key fingerprint、`validate-provenance` / `provenance-fingerprint`を追加済み。
- Unit 3: revision bundleのrequired documentへ`provenance.json`を追加し、bundle SHAへ反映済み。legacy bundleはfail-closed。
- Unit 4: incompleteまたは未承認provenance時のrun-context生成を停止。target resolutionはmetadata-onlyのまま維持。
- Unit 5: run-context metadata、promotion inspect、Parquet capsule metadataへmanifest fingerprintをbind済み。
- Unit 6: 親リポジトリ向け受領契約・責務分離資料を更新済み。外部repository/HF mutationは未実施。

検証結果:

```text
python provenance schema tests: PASS
cargo test --locked -p asr-contracts: PASS
cargo clippy --locked -p asr-contracts --all-targets -- -D warnings: PASS
cargo test --locked -p asr-capsule: PASS
cargo clippy --locked -p asr-capsule --all-targets -- -D warnings: PASS
cargo fmt --all -- --check: PASS
git diff --check: PASS
```

## Remaining evidence boundary

Parquet writer/readerはrun-contextのprovenance fingerprintをfile metadataへ保存・復元する。実private asset inventory、親側payloadとの実値一致、HF external proof、named platform runtime proofは未取得であり、実運用Parakeet routeはblockedのままとする。commit/pushは未実施。

## Next safe action

親リポジトリから実asset inventory付き`provenance.json`を受領した後、revision bundleへ投入し、complete + reviewed enablement、candidate transfer SHA、run-context/capsule/promotionの同一fingerprintをlocal integrationで検証する。
