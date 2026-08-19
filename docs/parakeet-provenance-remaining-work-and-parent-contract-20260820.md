# Parakeet provenance 残作業・親リポジトリ契約

作成日: 2026-08-20
対象 target: `parakeet-tdt_ctc-0.6b-ja`
対象 runtime profile set: `parakeet-tdt-ctc-v1`
関連親 issue: [#134](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/134)
関連実装入口: [`recursive-delivery-entry-20260820.md`](./recursive-delivery-entry-20260820.md)

## 1. この文書の目的

この文書は、#134対応のうち本リポジトリで実装済みの契約、残っている受入作業、親リポジトリから受領すべき入力、両リポジトリの責務境界を一つの参照先にまとめるものである。

ここでいう「実装完了」と「実運用route有効化」は別である。schema、validator、routing gate、fingerprint bindingは実装済みだが、親側の実asset inventoryが未受領であるため、現時点でParakeetのcanonical routeは有効化しない。

## 2. 現在の実装状態

| 領域 | 現在の状態 | 根拠 |
|---|---|---|
| 独立`provenance.json` schema | 実装済み | `evaluation/schemas/provenance.schema.json` |
| incomplete/complete/invalid fixture | 実装済み | `evaluation/provenance/fixtures/` |
| Rust strict validator | 実装済み | `rust/crates/asr-contracts/src/provenance.rs` |
| canonical fingerprint | 実装済み | `provenance-fingerprint`、sorted-key compact JSON SHA-256 |
| revision bundle | `provenance.json`必須・fail-closed | `rust/crates/asr-contracts/src/revisions.rs` |
| target resolve | metadata-only | `asr-hf resolve-target`は実行認可を行わない |
| canonical run-context | completeかつautomation enabled以外は停止 | `run_context_builder.rs` |
| capsule/Parquet | fingerprintをfile metadataへ保存・復元 | key: `jpapt.provenance.manifest_sha256` |
| promotion | run-contextのcomplete/enabled/fingerprintを再確認 | `asr-promotion inspect` |
| 親側実asset inventory | 未受領 | 現在のblocker |
| HF external proof / named platform runtime | 未取得 | この変更のscope外 |

## 3. 本リポジトリが受け入れる正本payload

親側から渡す正本ファイルは、revision bundle内の次の一ファイルである。

```text
revisions/provenance.json
```

schemaの正本は [`evaluation/schemas/provenance.schema.json`](../evaluation/schemas/provenance.schema.json) である。親側が管理する補助資料（source snapshot、candidate transfer report、license reportなど）は、`provenance.json`の各項目を説明する証跡として添付できるが、実行認可の入力はschemaに適合する`provenance.json`である。

### 3.1 必須トップレベル構造

```json
{
  "schema_version": 1,
  "status": "incomplete|complete",
  "automation_consumption": false,
  "target_id": "parakeet-tdt_ctc-0.6b-ja",
  "upstream": {"repo_id": "owner/name", "revision": "40-hex"},
  "development_repo": {"repo_id": "owner/name", "revision": "40-hex|sha256:...|snapshot-..."},
  "assets": [],
  "blockers": []
}
```

`status=complete`の場合、`assets`は空にできず、`blockers`は空でなければならない。情報不足を空文字、推測値、mutable tagで埋めてはならない。不明な情報は`status=incomplete`と具体的なblockerで返す。

### 3.2 assetごとの受領条件

各assetには次を必須とする。

- canonical relative `path`
- `kind`
- lowercase SHA-256
- `origin.repo_id`、immutable `origin.revision`、source `origin.path`
- 明示的な`license`
- 必要な`attribution`
- `transformation.kind/tool/version/input_sha256/output_sha256`
- candidateへ移送済みの場合は`candidate.path/sha256/role`

`transformation.output_sha256`はassetの`sha256`と一致し、candidate transferの`sha256`も対応するasset SHAと一致しなければならない。path traversal、absolute path、duplicate path、SHA不一致、origin/license/attribution/transformation欠落は拒否される。

### 3.3 automation enablement

`automation_consumption=true`はcomplete判定とは別のreviewed enablementである。trueにする場合、schemaが要求する`automation_enablement`に次を含める。

```json
{
  "review_id": "review-or-change-id",
  "approved_at": "RFC3339 timestamp",
  "approved_by": "identity",
  "policy_sha256": "64-hex"
}
```

complete fixtureの通過は、親側の実データが正しいことや、このreviewed enablementが承認済みであることを証明しない。

## 4. fingerprintと実行境界

manifest fingerprintは、JSON objectのkeyを再帰的に辞書順へ並べ、配列順を保持したcompact canonical JSONに対するSHA-256である。改行、pretty print、object key順だけの差でfingerprintが変わってはならない。

同一identityは次の経路で保持する。

```text
provenance.json
  -> revision bundle provenance.manifest_sha256
  -> run-context metadata.provenance.manifest_sha256
  -> run.parquet metadata jpapt.provenance.manifest_sha256
  -> promotion inspect
```

次のいずれかに該当する場合、canonical candidate fetch、evaluation、run-context生成、promotionを停止する。

- `provenance.json`が存在しない
- statusがcompleteでない
- `automation_consumption`がtrueでない
- target/repository identityが一致しない
- manifest fingerprintが一致しない
- candidate transfer SHAが一致しない

許可されるのはtarget metadataの静的解決、schema/validator test、incomplete diagnostic、実行準備を主張しないdry-runだけである。

## 5. 親リポジトリの責務

親リポジトリは次を実データに基づいて確定し、本リポジトリへ提供する。

1. private development repositoryのmaterial file inventory
2. exact upstream revisionとimmutable development snapshot/revision
3. 各assetのorigin repository/path/revision
4. assetごとのlicense、attribution、third-party notice
5. copied/converted/generated/modifiedの変換履歴とtool/version
6. candidate artifact path、candidate SHA、candidate roleとの対応
7. 親側Actions、GHCR、MCP、package、workflow artifactの外部証跡（必要な場合）
8. 上記情報を反映した`provenance.json`

親側のActions成功、GHCR packageのvisibility、MCP接続成功、HF Bucket URIの存在だけでは、asset provenance completeや本リポジトリのevaluation/promotion成功の代替にならない。

## 6. 本リポジトリの責務

本リポジトリは、親側の実データを推測・補完せず、次を担当する。

1. `provenance.schema.json`による構造検証
2. Rustによるstrict semantic validation
3. revision bundle SHAとmanifest fingerprintの計算
4. target、repository、asset path、SHA、transformation、candidate transferの整合性検証
5. incomplete provenanceのcanonical routing fail-closed
6. run-context、capsule、promotionへのfingerprint binding
7. evaluation、provider、parity、qualityの受入判断
8. accepted evidenceに基づくpromotion判断

親側のprivate repositoryを本リポジトリから探索して推測する責務はない。外部workflowの成功状態をlocal contractの成功証拠へ変換する場合も、digest/revision/identityが機械可読で渡されることを条件とする。

## 7. 残作業

### 7.1 親payload受領後に必須の作業

- [ ] 親側から実asset inventory付き`provenance.json`を受領
- [ ] upstream/development revisionがimmutableであることを確認
- [ ] asset origin/license/attribution/transformationを全件確認
- [ ] candidate transfer SHAとcandidate contractを照合
- [ ] `asr-contracts validate-provenance --path ... --target parakeet-tdt_ctc-0.6b-ja`を実行
- [ ] revision bundle全体を検証し、bundle SHA変更を記録
- [ ] reviewed enablementを別証跡として受領し、`automation_consumption=true`を確認
- [ ] canonical run-context生成を実行し、fingerprintを記録
- [ ] evaluation/capsule/promotionで同一fingerprintを検証

### 7.2 まだ外部証拠として残る作業

- [ ] HF Bucketのcandidate/reference/runs/benchmarks外部objectのdigest確認
- [ ] 親Actionsのworkflow run、artifact、head SHA、attemptの対応確認
- [ ] GHCR imageのdigest、package visibility、HF Jobs pullの段階的確認
- [ ] 実モデルを用いたfrontend/encoder/logits/token/text/quality検証
- [ ] providerごとの実行証拠（CPU/CUDA/DirectML/CoreMLの各境界）
- [ ] named platform runtime（Windows/macOSなど）の実機受入

これらはlocal fixtureがpassしても自動的には完了しない。

### 7.3 現時点で不要な作業

- 親リポジトリのissue/PR/Actions/GHCR/MCP設定を本リポジトリから変更すること
- 不明なrevision、license、attributionを推測で埋めること
- legacy bundleを自動補正して実行可能にすること
- 既存candidate/run artifactを書き換えること

## 8. 検証コマンドと証拠レベル

実装・contractの現行検証は次のとおり。

```text
cargo fmt --all -- --check
cargo check --locked --workspace
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
uv lock --check
uv run pytest -q python/tests/unit/test_provenance_schema.py
mise run doctor
git diff --check
```

これらはsource/static、unit、local integration、environment doctorの証拠である。HF external proof、親Actions proof、実モデルの品質、named platform runtime proofは含まれない。

## 9. 変更・ロールバック方針

親payload受領後も、まず専用revision bundleとtemporary runで検証する。検証失敗時は`status=incomplete`とblockerを維持し、既存candidate/run artifactを変更しない。automation enablementはprovenance completeの受領後に別レビューとして行う。

## 10. 受領完了の判定

次のすべてを満たすまで、#134対応を「実装済み・運用blocked」と表示する。

```text
exact upstream revision recorded
immutable development snapshot recorded
complete material asset inventory
asset-level origin/license/attribution/transformation complete
candidate transfer mapping and SHA match
provenance.json validates
reviewed automation enablement recorded separately
revision bundle and run-context fingerprint match
Parquet capsule fingerprint matches run-context
promotion revalidation passes
external HF/Actions/GHCR evidence is separately accepted
```

## 11. 関連資料

- [`recursive-delivery-entry-20260820.md`](./recursive-delivery-entry-20260820.md)
- [`parakeet-provenance-and-routing-responsibility.md`](./parakeet-provenance-and-routing-responsibility.md)
- [`parent-repository-current-spec-handoff-20260820.md`](./parent-repository-current-spec-handoff-20260820.md)
- [`parent-repository-issue-classification-20260820.md`](./parent-repository-issue-classification-20260820.md)
- [親リポジトリ issue #134](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/134)
