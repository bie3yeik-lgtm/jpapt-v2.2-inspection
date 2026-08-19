# Parakeet provenance / routing 責務分離

作成日: 2026-08-20
関連 issue: 親リポジトリ [#134](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/134)
対象 model: `nvidia/parakeet-tdt_ctc-0.6b-ja`
対象 development repo: `gawohok7/jpapt-v2.2-dev`

## 1. 目的

親リポジトリ issue #134 の内容を、現行 `jpapt-v2.2-inspection` の source-controlled contract と親リポジトリ固有の model/content provenance に分離する。

repository-level license metadata が一致していることだけでは、private development repository 内の全ファイルの origin、license、変換履歴、再配布可否を証明できない。したがって、provenance が未確定の状態で Parakeet route を自動有効化しない。

この文書の結論は次のとおり。

```text
upstream/model identity と evaluation routing の authority
    -> jpapt-v2.2-inspection

private development repo 内の実ファイル、コピー元、変換、attribution
    -> 親リポジトリ / asset owner

candidate ONNX artifact の実体、hash、runtime contract
    -> jpapt-v2.2-inspection の candidate/evaluation boundary
```

## 2. 判定原則

- repository-level `license` metadata を asset-level provenance の代用にしない。
- README の関係記述を exact revision の証明にしない。
- upstream revision、private development revision、candidate artifact revisionを混同しない。
- ONNX は deployment artifactであり、canonical source modelではない。
- provenance が不完全な target は、候補生成・routing・promotionへ fail-closed で進めない。
- `config/current.json` の mutable pointerは、immutable revision bundleの代わりにしない。
- candidate byte identityは HF URI ではなく、実体の相対path、size、SHA-256、bundle SHAで固定する。
- `automation_consumption` は provenance complete から自動的に有効化しない。routing enablementは別の reviewed changeとする。

## 3. 事実と未確定事項

### 確認済みの関係

```text
nvidia/parakeet-tdt_ctc-0.6b-ja
    -> Japanese ASR / NeMo upstream model
    -> ONNX deployment/evaluation work
gawohok7/jpapt-v2.2-dev
```

現行 target routing は、少なくとも次を repository contract から導出する。

```text
target_id                 = parakeet-tdt_ctc-0.6b-ja
profile_set               = parakeet-tdt-ctc-v1
default runtime variant   = ctc
Rust evaluator capability = ctc
framework                 = nemo
development Bucket        = gawohok7/jpapt-v2.2-dev-bucket
development Model Repo    = gawohok7/jpapt-v2.2-dev
upstream repository       = nvidia/parakeet-tdt_ctc-0.6b-ja
tokenizer repository      = nvidia/parakeet-tdt_ctc-0.6b-ja
```

### まだ証明できていない事項

以下は repository-level metadata だけでは確定しない。

- upstream exact commit/revision
- private development repo の material file tree
- model weights/checkpoints の origin と exact revision
- NeMo config と local modification
- tokenizer/vocabulary の origin と modification
- copied/new scripts の copyright/license
- generated/converted ONNX、tensor、metadata の transformation chain
- docs/model card/attribution の保持状況
- third-party asset とその利用条件
- private development repo から candidate artifact へ移した byte-level関係

なお、現行の HF revision fetch でも remote `config/current.json` の旧フィールド名や必須 `runtime.json` 欠落を正規化してはいけない。revision bundleが現行 contractを満たさない場合は、provenance と同じく fail-closed とする。

## 4. `jpapt-v2.2-inspection` の責務

### 4.1 source-controlled model/routing contract

本 repository は、親リポジトリや mutable HF metadataから推測せず、次を source-controlled contractとして保持・検証する。

- target ID
- upstream repository ID
- development Bucket / Model Repo identity
- tokenizer repository identity
- framework
- profile set
- runtime variant / decoder capability
- provider compatibility
- expected environment
- dataset/revision bundleの required shape

主な authority:

```text
config/asr-catalog.json
config/hf-targets/*.toml
config/models/*.toml
config/providers/*.toml
config/environments/*.toml
config/evaluation/*.toml
evaluation/schemas/*.schema.json
rust/crates/asr-contracts
rust/crates/asr-hf
```

### 4.2 revision lock と取得

本 repository は、評価に使う upstream/dataset/runtime/config identityを revision lock に固定する。

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

`current.json` は mutable selection pointerであり、`config/versions/config-NNNNNN/` の immutable bundleを選ぶためだけに使う。旧 field名、欠落 document、floating revisionは自動修復せず拒否する。

### 4.3 candidate artifact provenance

candidateのhuman-authored metadataは最小限にし、実 artifactから次を生成・検証する。

- canonical relative path
- artifact role
- file size
- file SHA-256
- ONNX graph input/output
- tokenizer path/kind
- runtime variant/decoder
- candidate bundle SHA-256
- catalog/profile/decoder identity

candidate は upstream provenanceの代替ではない。candidate artifactが正しく検証できても、origin/revision/licenseが不明な private source assetを自動的に承認してはならない。

### 4.4 evaluation / promotion gate

provenanceが評価対象として受理されるまで、少なくとも次を必須にする。

```text
target identity valid
revision bundle valid
candidate contract valid
candidate bundle SHA valid
dataset lock valid
run-context frozen
provider evidence valid
accepted full run
promotion re-fetch/re-validation passed
```

`acceptance.passed == true` だけでは provenance complete を意味しない。source provenance、candidate artifact identity、evaluation acceptanceを別々に保持する。

### 4.5 実装すべき追加 contract

本 repository 側で必要な実装は次の順序とする。

1. provenance manifest schemaを追加する。
2. manifestで upstream repo/revision、asset path/kind、origin revision、license、transformation、blockerを表現する。
3. RustまたはRustから呼び出す検証入口で、complete判定を fail-closed にする。
4. target routingは provenance complete を参照するが、`automation_consumption` の有効化は別の変更として要求する。
5. candidate publish/evaluation/promotionで、provenance manifest fingerprintをrun-context/evidenceへ bindする。
6. provenance未完了時の診断を machine-readable な error code として保存する。

manifest例:

```json
{
  "schema_version": 1,
  "status": "incomplete",
  "automation_consumption": false,
  "target_id": "parakeet-tdt_ctc-0.6b-ja",
  "upstream": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision": null
  },
  "development_repo": {
    "repo_id": "gawohok7/jpapt-v2.2-dev",
    "revision": null
  },
  "assets": [],
  "blockers": [
    "EXACT_UPSTREAM_REVISION_REQUIRED",
    "MATERIAL_ASSET_INVENTORY_REQUIRED",
    "TRANSFORMATION_CHAIN_REQUIRED"
  ]
}
```

`status=complete` は、次をすべて満たさない限り受理しない。

- exact lowercase 40-hex upstream revision
- development repo revisionまたはimmutable content identity
- material asset 1件以上
- 各assetの path/kind/origin repo/origin revision/license/transformation
- blockersが空
- schema / target / repository identityが一致

## 5. 親リポジトリの責務

親リポジトリが private development repo または application integration を所有する場合、次を確定する。

### 5.1 private repository の inventory

親側は、実際に `gawohok7/jpapt-v2.2-dev` に存在する material contentを取得し、次を記録する。

```text
repository_id
exact repository revision or immutable snapshot
canonical relative path
asset kind
byte size / SHA-256 where applicable
origin repository
origin revision
license / attribution
transformation
generated/copied/new classification
```

対象は少なくとも以下とする。

- weights/checkpoints
- NeMo config
- tokenizer/vocabulary
- ONNX encoder/decoder/joint等
- scripts/code
- model card/docs/attribution
- generated tensors/metadata
- third-party assets

### 5.2 upstreamとの関係の証明

親側は、READMEやrepository-level licenseだけでなく、assetごとに次を示す。

- upstreamのどのrevisionから来たか
- そのままコピーか、変換・再生成か
- 変換に使ったtool/version/config
- local modificationの有無
- resulting artifactの再配布条件

### 5.3 candidate transferの証拠

private development repoから candidate Bucketへ移す場合、親側は次の対応表を保存する。

```text
source asset path / SHA-256
candidate artifact path / SHA-256
transformation identity
candidate bundle SHA-256
transfer time
source revision
target candidate ID
```

HF Bucket URIだけをsource identityとして保存しない。Bucketの同一URIが後で変更されても、過去のcandidate provenanceを上書きできない形にする。

### 5.4 本 repositoryへ渡す payload

親側から本 repositoryへ渡す最小情報は、推測値ではなく以下の machine-readable documentとする。

```text
provenance_manifest.json
source_snapshot.json
candidate_transfer.json
```

不足情報は `null` と blockerで表現し、親側で「metadataから推測したcomplete」を生成しない。

## 6. 共同責務と境界

| 判断 | 本 repository | 親 repository |
|---|---|---|
| `nvidia/parakeet-tdt_ctc-0.6b-ja` をtargetとして登録する | 担当 | 参照のみ |
| exact upstream revisionをsource assetとして確定する | validator/acceptance | inventoryの提供元 |
| private development repoの全material fileを棚卸しする | 受領・検証 | 担当 |
| candidate ONNXのgraph/runtime contractを検証する | 担当 | 実 artifactを提供 |
| candidate bundle SHAを生成する | 担当 | sourceとの対応表を提供 |
| license/attribution/transformationのasset-level証明 | 受領条件・fail-closed | 担当 |
| revision bundleのschema/sha検証 | 担当 | input提供 |
| evaluation quality/provider/parity | 担当 | 必要な実行環境・入力を提供 |
| promotion gate | 担当 | accepted evidenceを消費 |
| external completion/ACK/lifecycle | protocol authority | receiver capabilityを提供する場合のみ |
| private GitHub Actions / package settings | 依存しない | 親側運用責務 |

## 7. 未完了状態の扱い

provenanceが未完了の場合:

```text
候補routing       = blocked
candidate publish = blockedまたはprovenance未完了を明示
evaluation        = provenanceがacceptedでない限りcanonical評価にしない
promotion         = blocked
release           = blocked
```

ただし、schema/validatorそのものの deterministic contract testは、実モデル・実private assetを使わずに実行してよい。これは provenance complete の証明ではない。

## 8. 完了判定

#134を現行仕様上で完了とするには、次の全条件が必要である。

```text
exact upstream revision is recorded
private development snapshot is immutable or revision-pinned
material asset inventory is complete
asset-level origin/license/transformation is recorded
candidate transfer mapping is recorded
provenance manifest validates
automation_consumption is enabled only by a separate reviewed change
candidate contract and bundle SHA validate
evaluation run-context binds provenance fingerprint
promotion revalidates all identities
```

repository metadataのlicense一致、READMEの関係記述、candidateのtranscript成功、HF Bucket URIの存在だけでは完了としない。

## 9. 親リポジトリへの伝達事項

実装着手後の正本入口は [`recursive-delivery-entry-20260820.md`](./recursive-delivery-entry-20260820.md) である。本 repository側では、`evaluation/schemas/provenance.schema.json`、Rust `asr-contracts` validator/fingerprint、revision bundle必須化、run-context/promotionのenablement gateまでを担当する。実asset inventoryが未受領のため、実運用routeは引き続きblockedであり、fixtureのcompleteは実assetのcompleteを意味しない。

生成された`run.parquet`については、run-context metadataの`provenance.manifest_sha256`を`jpapt.provenance.manifest_sha256`としてParquet file metadataへ保存し、Rust readerが復元する。これはJSON/JSONLの実asset provenanceを新規生成するものではなく、受領済みrun-context identityの保存・検査境界である。

親リポジトリへは、次を伝える。

1. #134の本質は「license metadataの不一致」ではなく、asset-level provenanceとcandidate transfer identityの欠落である。
2. 本 repositoryは provenance incomplete のままrouteを自動有効化しない。
3. 親側は private development repoの実file inventory、exact revision、変換履歴、attributionを提供する責務がある。
4. 本 repositoryは受領したmanifestをschema/Rust contractで検証し、candidate/evaluation/promotionへbindする。
5. 親 private Actions、GHCR Public設定、MCP connector状態は、provenance completeの代替証拠ではない。
6. 推測でrevisionやlicenseを補完せず、不明な項目はblockerとして返す。

## 10. 参照資料

- [親 issue #134](https://github.com/largoyo/Premiere-AutoProcess-Plugin/issues/134)
- [docs/README.md](README.md)
- [docs/contracts.md](contracts.md)
- [docs/architecture.md](architecture.md)
- [docs/evaluation.md](evaluation.md)
- [docs/workflows.md](workflows.md)
- [docs/parent-repository-issue-classification-20260820.md](parent-repository-issue-classification-20260820.md)
- [docs/parent-repository-current-spec-handoff-20260820.md](parent-repository-current-spec-handoff-20260820.md)
