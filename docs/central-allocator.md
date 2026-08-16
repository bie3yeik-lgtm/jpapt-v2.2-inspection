# 中央HF Allocator

## 目的

`candidate_id`、`experiment_id`、`config_version` の数値suffixは人間が決めません。複数Repositoryから同じBucketを利用しても重複しないよう、本Repositoryの `HF Central Sequence Allocator` を唯一の採番実行点とします。

```text
Repo A ─┐
Repo B ─┼─> HF Central Sequence Allocator -> HF Bucket
Repo C ─┘
```

---

## Allocation policyのSource of Truth

prefix文字列はASR runtime catalogではなく、専用の次のcatalogへ集約します。

```text
config/hf-allocation-catalog.json
```

例:

```json
{
  "schema_version": 1,
  "catalog_id": "hf-allocation-catalog-v1",
  "prefixes": {
    "candidate.default": "candidate",
    "candidate.parakeet-tdt-ctc-v1": "parakeet-candidate",
    "candidate.whisper-autoregressive-v1": "whisper-candidate",
    "experiment.cpu_full": "cpu-full-eval",
    "experiment.cross_platform_parity": "cross-platform-parity",
    "experiment.rust_eval": "rust-eval",
    "config.version": "config"
  }
}
```

workflow/scriptは表示prefixではなくsemantic keyを渡します。

```text
experiment.cpu_full -> cpu-full-eval -> cpu-full-eval-000042
```

`config/asr-catalog.json` はASR runtime semantics専用であり、採番prefixを置きません。

---

## 対象collection

```text
candidates   <resolved-prefix>-NNNNNN
experiments  <resolved-prefix>-NNNNNN
config       config-NNNNNN
```

数値suffixはprefixごとではなくcollection全体で共有します。

```text
experiments/
  cpu-full-eval-000002/
  graph-opt-000006/
  rust-eval-000009/
```

次の採番はprefixに関係なく`000010`です。

---

## 採番アルゴリズム

```text
1. 対象Bucket collectionを再帰list
2. 既存6桁suffixを抽出
3. 最大suffix + 1
4. allocation catalogからprefixを解決
5. ID直下README.mdを書いて予約
6. Bucket root READMEのallocator statusを更新
7. allocation.jsonを返却
```

`000001`が構造例として存在すれば最初の実運用IDは`000002`です。

予約後にpublishが失敗しても番号は再利用しません。

---

## 排他制御

中央workflowのconcurrencyはBucket単位です。

```yaml
concurrency:
  group: hf-central-sequence-${{ inputs.hf_bucket }}
  cancel-in-progress: false
```

Bucket全体を直列化する理由は、各collectionの採番に加えてBucket root `README.md`も共有更新するためです。

---

## 呼出経路

通常入口:

```text
scripts/hf/hf-request-id.sh
```

互換入口:

```text
scripts/hf/hf-allocate-id.sh
```

通常実行の`hf-allocate-id.sh`は中央workflowへ転送します。`list -> max+1`を直接実行できるのは`HF_ALLOCATOR_INTERNAL=1`を設定した中央workflowだけです。

---

## allocation.json

中央Allocatorの返却contractはschema v3です。

```json
{
  "schema_version": 3,
  "request_id": "...",
  "id": "cpu-full-eval-000042",
  "bucket": "namespace/bucket",
  "collection": "experiments",
  "allocation_catalog": {
    "id": "hf-allocation-catalog-v1",
    "sha256": "<ALLOCATION_CATALOG_SHA256>"
  },
  "prefix_key": "experiment.cpu_full",
  "resolved_prefix": "cpu-full-eval"
}
```

これによりprefix名称が将来変更されても、採番時にどのpolicy snapshotを使用したか追跡できます。

`allocation.json`はActions間の応答contractであり、Bucketの長期保存正本ではありません。ID直下READMEとBucket root READMEが永続的な人間向け履歴です。

---

## Candidate prefix解決

Candidate側はmanual prefixを持ちません。

```text
metadata.profile_set
    ↓
hf-allocation-catalog.json
    ↓
candidate.<profile_set>
    ↓
resolved prefix
```

例:

```text
parakeet-tdt-ctc-v1
    -> candidate.parakeet-tdt-ctc-v1
    -> parakeet-candidate
```

未登録profile setは`candidate.default`へfallbackします。

---

## Experiment prefix解決

workflowは以下のsemantic keyを使用します。

```text
CPU Full                 experiment.cpu_full
Cross Platform Parity    experiment.cross_platform_parity
Rust Evaluation          experiment.rust_eval
```

`cpu-full-eval`等のraw文字列をworkflowへ複製しません。

---

## Config version

config versionは常に、

```text
config.version -> config -> config-NNNNNN
```

として中央Allocatorから取得します。

`hf-push-config-version.sh`は、

```text
local config validation
    ↓
central allocation
    ↓
4 JSON upload
    ↓
全upload成功後のみ current.json更新
```

の順で処理します。

---

## Bucket root README

採番のたびに、

```text
hf://buckets/<namespace>/<bucket>/README.md
```

のmarker内だけを更新します。

```html
<!-- hf-central-allocator:start -->
...
<!-- hf-central-allocator:end -->
```

表示内容:

```text
last allocation
candidates current maximum
experiments current maximum
config current maximum
updated timestamp
```

marker外の説明は保持します。

ここでの番号はpublish済み最大番号ではなく**予約済み最大番号**です。

---

## 認証

同一Repository:

```yaml
GH_TOKEN: ${{ secrets.HF_ALLOCATOR_GITHUB_TOKEN || github.token }}
```

他Repositoryから利用する場合は、呼出元に`HF_ALLOCATOR_GITHUB_TOKEN`を設定します。中央Repositoryのworkflow dispatch/readおよびartifact readに必要な権限を与えます。

呼出先は次でoverrideできます。

```text
HF_ALLOCATOR_REPOSITORY
HF_ALLOCATOR_WORKFLOW
HF_ALLOCATOR_REF
```

既定:

```text
HF_ALLOCATOR_REPOSITORY=bie3yeik-lgtm/jpapt-v2.2-inspection
HF_ALLOCATOR_WORKFLOW=hf-central-allocator.yml
HF_ALLOCATOR_REF=main
```

---

## 不変条件

1. 数値suffixを人間が決めない。
2. 予約済み番号を再利用しない。
3. prefixが変わってもcollection全体の連番を継続する。
4. 複数Repositoryからの採番は必ず中央Allocatorを通す。
5. raw prefixをworkflow/scriptへ複製しない。
6. prefix policyは`hf-allocation-catalog.json`だけで管理する。
7. ASR runtime semanticsは`asr-catalog.json`へ分離する。
8. Bucket routingが変わっても、その時点の物理Bucketの最大suffixから継続する。
