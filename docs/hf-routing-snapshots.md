# Hugging Face Routing Snapshot

## 目的

`HF_TARGETS_JSON`はmodel identity registryではなく、**現在時点のstorage routing**を表します。この点を過去runの再現性と混同しないための仕様を定義します。

## 現在snapshotのルール

1つの`HF_TARGETS_JSON`内では次を必須とします。

- target keyは一意
- `HF_BUCKET`は一意
- 各targetは1つの`HF_BUCKET`と`HF_MODEL_REPO`を持つ
- Bucketからtargetを一意に逆引きできる

例:

```json
{
  "model-a": {
    "HF_BUCKET": "owner/bucket-a",
    "HF_MODEL_REPO": "owner/model-a"
  },
  "model-b": {
    "HF_BUCKET": "owner/bucket-b",
    "HF_MODEL_REPO": "owner/model-b"
  }
}
```

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

`reference.json`はmodel provenanceを固定します。

```text
development_artifact
upstream
tokenizer
reference
decoder contract
```

一方、`HF_BUCKET`は運用上の保存場所です。

```text
reference.json   = provenance
HF_TARGETS_JSON  = current routing
run-context.json = execution-time routing snapshot
```

## Runに保存するrouting snapshot

過去runは現在のRepository Variableから推測しません。実行時点で次をrun metadataへ保存します。

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

再現時の参照順:

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

## 自動採番への影響

Candidate/Experimentの連番は物理Bucket内のcollectionを走査して決めます。

```text
<bucket>/candidates/
<bucket>/experiments/
```

Targetが別Bucketへ移った場合、移動先Bucketに存在する最大suffix+1から続行します。Target専用の恒久counterではありません。

## 運用上の不変条件

```text
現在snapshot内のHF_BUCKETは一意
routingは将来変更可能
Bucketをmodel identityとして扱わない
reference.jsonへHF_BUCKETを書かない
runへ実行時routingを保存する
過去runは現在routingから推測しない
```

この分離により、storage再編とmodel provenanceを独立して変更できます。