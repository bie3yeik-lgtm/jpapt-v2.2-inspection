# 中央HF Allocator

## 目的

`candidate_id`、`experiment_id`、`config_version` の連番と表示prefixを各Workflowへ分散させません。

```text
Repo A ─┐
Repo B ─┼─> HF Central Sequence Allocator
Repo C ─┘              |
                       v
                Hugging Face Bucket
```

中央Allocatorが管理するものは2種類です。

```text
prefix policy     config/asr-catalog.json
sequence number   実Bucket内の既存最大suffix + 1
```

---

## Semantic prefix key

Workflow/scriptはraw prefixを指定しません。

禁止:

```bash
hf-allocate-id.sh experiments cpu-full-eval
hf-allocate-id.sh experiments rust-eval
```

正規形:

```bash
hf-allocate-id.sh experiments experiment.cpu_full
hf-allocate-id.sh experiments experiment.rust_eval
```

中央catalog:

```json
{
  "id_prefixes": {
    "candidate.parakeet": "parakeet-candidate",
    "candidate.whisper": "whisper-candidate",
    "experiment.cpu_full": "cpu-full-eval",
    "experiment.cross_platform_parity": "cross-platform-parity",
    "experiment.rust_eval": "rust-eval",
    "config.version": "config"
  }
}
```

解決例:

```text
experiment.cpu_full
        ↓
cpu-full-eval
        ↓ max suffix + 1
cpu-full-eval-000123
```

命名を変更するときは`config/asr-catalog.json`だけを変更します。

---

## Candidate prefix

Candidate publish時に人間はprefixを指定しません。

```text
metadata.json.profile_set
        ↓
config/asr-catalog.json.profile_sets
        ↓ candidate_prefix_key
candidate.parakeet
        ↓ id_prefixes
parakeet-candidate
        ↓ allocator
parakeet-candidate-000123
```

したがって次のような呼出は拒否します。

```bash
hf-push-candidate.sh ./candidate my-custom-prefix
```

正規形:

```bash
hf-push-candidate.sh ./candidate
```

---

## 対象collection

```text
candidates   <catalog-resolved-prefix>-NNNNNN
experiments  <catalog-resolved-prefix>-NNNNNN
config       config-NNNNNN
```

数値suffixはprefixごとではなくcollection全体で共有します。

```text
experiments/
  cpu-full-eval-000002/
  cross-platform-parity-000006/
  rust-eval-000009/
```

次にどのexperiment prefix keyを使ってもsuffixは`000010`です。

---

## 採番アルゴリズム

```text
1. semantic prefix keyをASR catalogで検証
2. prefix文字列へ解決
3. 対象Bucket collectionを再帰list
4. 全IDから6桁suffixを抽出
5. 最大suffix + 1
6. README.mdを書いて予約
7. BucketルートREADME.mdを更新
8. allocation.jsonをcallerへ返す
```

`000001`が構造例として存在すれば、最初の実運用番号は`000002`になります。

---

## 排他制御

中央workflowはBucket単位で直列化します。

```yaml
concurrency:
  group: hf-central-sequence-${{ inputs.hf_bucket }}
  cancel-in-progress: false
```

理由:

```text
candidate/config/experiment allocation
        +
Bucket root README update
```

を1つのcritical sectionとして扱うためです。

---

## 呼出経路

公開入口:

```text
scripts/hf/hf-request-id.sh
```

互換入口:

```text
scripts/hf/hf-allocate-id.sh
```

通常の`hf-allocate-id.sh`は中央clientへ転送されます。

低レベルの、

```text
list -> max + 1 -> reserve
```

を実行できるのは`HF_ALLOCATOR_INTERNAL=1`を設定した中央workflowだけです。

---

## allocation.json

中央Allocatorのresponseはschema v2です。

```json
{
  "schema_version": 2,
  "request_id": "...",
  "id": "cpu-full-eval-000123",
  "bucket": "namespace/bucket",
  "collection": "experiments",
  "prefix_key": "experiment.cpu_full",
  "resolved_prefix": "cpu-full-eval"
}
```

`prefix_key`を保存することで、将来表示prefixが変更されても何の用途で発行されたIDか追跡できます。

---

## 認証

### 同一Repository

```yaml
GH_TOKEN: ${{ secrets.HF_ALLOCATOR_GITHUB_TOKEN || github.token }}
```

### 他Repository

呼出元に、

```text
HF_ALLOCATOR_GITHUB_TOKEN
```

を用意します。

必要に応じて、

```text
HF_ALLOCATOR_REPOSITORY
HF_ALLOCATOR_WORKFLOW
HF_ALLOCATOR_REF
```

を変更できます。

既定:

```text
HF_ALLOCATOR_REPOSITORY=bie3yeik-lgtm/jpapt-v2.2-inspection
HF_ALLOCATOR_WORKFLOW=hf-central-allocator.yml
HF_ALLOCATOR_REF=main
```

---

## BucketルートREADME

採番ごとに、

```text
hf://buckets/<namespace>/<bucket>/README.md
```

のmanaged blockを更新します。

```html
<!-- hf-central-allocator:start -->
...
<!-- hf-central-allocator:end -->
```

marker外は変更しません。

表示する番号は「publish成功番号」ではなく**予約済み最大番号**です。採番後にpublishが失敗しても番号は再利用しません。

---

## Candidate publish

```text
schema-v3 metadata
    ↓
profile_set
    ↓
candidate_prefix_key
    ↓
Central Allocator
    ↓
candidate_id bind
    ↓
全runtime variant再検証
    ↓
Bucket publish
```

---

## Config publish

config prefixもcatalogの、

```text
config.version -> config
```

から解決します。

`hf-push-config-version.sh`は、

```text
reference.json
evaluation-schema.json
datasets-lock.json
```

を受け取り、target/profile setから`runtime.json`を自動生成します。

```text
3 user/source JSON
    ↓
runtime.json生成
    ↓
strict validation
    ↓
config.versionで中央採番
    ↓
4 JSON upload
    ↓
config/current.json更新
```

`runtime.json`を手作業で複製する必要はありません。

---

## Experiment allocation

現在のsemantic key:

```text
experiment.cpu_full
experiment.cross_platform_parity
experiment.rust_eval
```

matrix評価では1つのexperiment IDを共有し、provider/environmentごとに別run IDを生成します。

runtime variantはallocation provenanceにも記録します。

---

## 運用上の不変条件

1. 数値suffixを人間が決めない。
2. raw prefixをWorkflow/scriptへ記述しない。
3. prefixはsemantic key経由でASR catalogから解決する。
4. 予約済み番号を再利用しない。
5. prefixが変わってもcollection全体の連番は継続する。
6. 複数Repositoryからの採番は必ず中央Allocatorを通す。
7. BucketルートREADMEのmanaged blockは手動編集しない。
8. `config/current.json`のversion番号も中央Allocatorで発行する。
9. Bucket routingが変わっても採番はその物理Bucket内の最大suffixから継続する。
