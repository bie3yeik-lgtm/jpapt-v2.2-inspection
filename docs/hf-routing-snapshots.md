# Hugging Face Routing Snapshot

## 目的

`HF_TARGETS_JSON`はmodel identity registryではなく、**現在時点のstorage routing**を表します。この点を過去runの再現性と混同しないための仕様を定義します。

## 現在snapshotのルール

1つの`HF_TARGETS_JSON`内では次を必須とします。

- target keyは一意
- `HF_BUCKET`は一意
- 各targetは1つの`HF_BUCKET`と`HF_MODEL_REPO`を持つ
- Bucketからtargetを一意に逆引きできる

同一snapshotで2 targetが同じ`HF_BUCKET`を持つ構成は無効です。

## 過去との対応変更は許容する

一意性は**同じsnapshot内**の制約です。将来、容量・用途・migrationの都合でroutingを変更できます。

```text
時点T1
model-a -> bucket-a
model-b -> bucket-b

時点T2
model-a -> bucket-c
model-b -> bucket-a
```

これは有効です。Bucketはtargetの恒久identityではありません。

## `reference.json`にBucketを書かない理由

```text
reference.json   = model provenance
HF_TARGETS_JSON  = current routing
run-context.json = execution-time routing snapshot
```

`reference.json`は:

```text
development_artifact
upstream
tokenizer
reference
decoder contract
```

を固定します。`HF_BUCKET`は運用上の保存場所なので含めません。

## Runに保存するrouting snapshot

実行時点で次をrun metadataへ保存します。

```text
metadata.hf_target_id
metadata.hf_bucket
metadata.hf_model_repo
```

加えて:

```text
revisions.config_version
artifact.candidate_id
metadata.experiment_id
```

を使えば、当時の実行対象を特定できます。

## 過去runの再現

```text
run-context.metadata.hf_bucket
  ↓
当時のBucket

run-context.revisions.config_version
  ↓
当時のversioned config

run-context.artifact.candidate_id
  ↓
当時のcandidate
```

例:

```bash
export HF_BUCKET="<historical-bucket>"
export HF_CONFIG_VERSION="config-000023"

bash scripts/hf/hf-fetch-revisions.sh
bash scripts/hf/hf-fetch-candidate.sh "<candidate-id>"
```

その後artifact SHA-256とrevision bundle hashを比較します。

## Resolverの責務

`scripts/ci/resolve-hf-target.py`は現在snapshotだけを検証します。

検出するもの:

```text
malformed JSON
missing HF_BUCKET
missing HF_MODEL_REPO
duplicate HF_BUCKET in current snapshot
unknown bucket
```

検出しないもの:

```text
過去snapshotとのBucket変更
過去に別targetが使っていたBucketの再利用
```

これらは正常なrouting変更です。

## 中央Allocatorへの影響

Candidate、Experiment、Config Versionの連番はtargetではなく**物理Bucket内のcollection**に属します。

```text
<bucket>/candidates/
<bucket>/experiments/
<bucket>/config/versions/
```

Targetが別Bucketへ移った場合、移動先Bucketの既存最大suffix+1から続行します。Target専用の恒久counterではありません。

複数Repositoryがその移動先Bucketを利用していても、全採番要求は中央Allocatorへ集約されます。

```text
Repo A ─┐
Repo B ─┼─> Central Allocator -> destination Bucket
Repo C ─┘
```

したがってrouting変更後も、各Repositoryが独自にcounterを持つことはありません。

## BucketルートREADME

中央Allocatorは採番のたびにBucketルート`README.md`へ現在最大番号を更新します。

```text
candidates 現在番号
experiments 現在番号
config 現在番号
```

routing変更後にtargetが別Bucketへ移動した場合、この表示も移動先Bucketの物理履歴を表します。target固有の累積番号ではありません。

過去の番号・pathはrun-contextの`hf_bucket`とcandidate/config identityの組み合わせで追跡します。

## 運用上の不変条件

```text
現在snapshot内のHF_BUCKETは一意
routingは将来変更可能
Bucketをmodel identityとして扱わない
reference.jsonへHF_BUCKETを書かない
runへ実行時routingを保存する
過去runは現在routingから推測しない
採番counterはtargetではなく物理Bucket collectionに属する
複数Repositoryの採番は中央Allocatorへ集約する
```

この分離により、storage再編、model provenance、採番履歴をそれぞれ独立して管理できます。

関連文書:

```text
docs/central-allocator.md
docs/hf-bucket-operations.md
docs/hf-layout.md
```
