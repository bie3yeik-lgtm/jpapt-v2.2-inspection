# 中央HF Allocator

## 目的

`candidate_id`、`experiment_id`、`config_version` の連番は、人間が決める識別子ではありません。複数Repositoryが同じHugging Face Bucketを利用しても重複しないよう、本リポジトリの `HF Central Sequence Allocator` workflowを唯一の採番実行点として使用します。

```text
Repo A ─┐
Repo B ─┼─> HF Central Sequence Allocator
Repo C ─┘              |
                       v
                Hugging Face Bucket
```

各Repositoryは採番そのものを行わず、中央Allocatorへ要求を送ります。

## 対象collection

中央Allocatorは次の3種類を管理します。

```text
candidates   <prefix>-NNNNNN
experiments  <prefix>-NNNNNN
config       config-NNNNNN
```

数値suffixはprefixごとではなくcollection全体で共有します。

例:

```text
experiments/
  cpu-full-eval-000002/
  graph-opt-000006/
  rust-eval-000009/
```

次にどのprefixを使っても数値部分は `000010` です。

## 採番アルゴリズム

中央workflowは次を行います。

```text
1. 対象Bucketのcollectionを再帰list
2. 6桁suffixを持つ既存IDを抽出
3. 最大suffixを取得
4. +1
5. README.mdを書いて予約
6. BucketルートREADME.mdのAllocator状態を更新
7. allocation.jsonをGitHub Actions artifactとして返却
```

`000001` が構造例として存在すれば、最初の実運用IDは自然に `000002` になります。

## 排他制御

中央workflowのconcurrencyは **Bucket単位** です。

```yaml
concurrency:
  group: hf-central-sequence-${{ inputs.hf_bucket }}
  cancel-in-progress: false
```

collection単位ではなくBucket全体を直列化する理由は、採番後にBucketルートの共通 `README.md` を更新するためです。

これにより、異なるRepositoryから同じBucketへ同時に要求が来ても、次の処理は同時実行されません。

```text
list -> max + 1 -> reservation -> root README update
```

## 呼出経路

通常の入口は:

```text
scripts/hf/hf-request-id.sh
```

互換入口として:

```text
scripts/hf/hf-allocate-id.sh
```

も残しますが、`HF_ALLOCATOR_INTERNAL=1` がない通常実行では自動的に `hf-request-id.sh` へ転送されます。

低レベルの `list -> max+1` を直接実行できるのは中央workflowだけです。

## 認証

### このRepository内のActions

workflowでは次を使用します。

```yaml
GH_TOKEN: ${{ secrets.HF_ALLOCATOR_GITHUB_TOKEN || github.token }}
```

同一Repositoryであれば通常は `github.token` で中央workflowをdispatchできます。

### 他Repositoryから利用する場合

呼出元Repositoryに次のSecretを用意します。

```text
HF_ALLOCATOR_GITHUB_TOKEN
```

このtokenには少なくとも中央Allocator Repositoryに対するActions workflow dispatch/readとartifact readに必要な権限を付与します。

呼出先は必要に応じて次で変更できます。

```text
HF_ALLOCATOR_REPOSITORY
HF_ALLOCATOR_WORKFLOW
HF_ALLOCATOR_REF
```

既定値:

```text
HF_ALLOCATOR_REPOSITORY=bie3yeik-lgtm/jpapt-v2.2-inspection
HF_ALLOCATOR_WORKFLOW=hf-central-allocator.yml
HF_ALLOCATOR_REF=main
```

## BucketルートREADME

採番のたびに:

```text
hf://buckets/<namespace>/<bucket>/README.md
```

の管理ブロックを更新します。

管理対象は次のmarker内だけです。

```html
<!-- hf-central-allocator:start -->
...
<!-- hf-central-allocator:end -->
```

marker外の人間が書いた説明は維持されます。

自動表示例:

```text
Central Allocator 状態

最終更新: ...
直近の採番: experiments/cpu-full-eval-000010
candidates 現在番号: 000008 (...-000008)
experiments 現在番号: 000010 (...-000010)
config 現在番号: 000004 (config-000004)
```

ここで示す番号は「最後に成功したartifact publish番号」ではなく **Allocatorが予約済みの最大番号** です。採番後のpublishが失敗しても、その番号は再利用しません。

## Candidate publish

```text
hf-push-candidate.sh
  -> central allocatorへcandidate ID要求
  -> candidates/<id>/README.md予約
  -> local metadata.jsonへcandidate_id反映
  -> candidate artifact sync
```

## Config publish

```text
hf-push-config-version.sh
  -> revision bundleをlocal strict validation
  -> central allocatorへconfig version要求
  -> config/versions/config-NNNNNN/README.md予約
  -> 3 revision JSONをupload
  -> 全upload成功後にconfig/current.json更新
```

採番だけ成功してpublishが失敗した場合、空番ではなく予約済み履歴として残します。`current.json` は未完成versionを指しません。

## Experiment allocation

`CPU Full Evaluation`、`Cross Platform ONNX Parity`、`Rust Cross Platform Evaluation` は実験開始時に中央Allocatorへ要求します。

```text
cpu-full-eval-NNNNNN
cross-platform-parity-NNNNNN
rust-eval-NNNNNN
```

matrix評価では1つのexperiment IDを共有し、各実行は別々のrun IDを持ちます。

## 運用上の不変条件

1. 数値suffixを人間が決めない。
2. 予約済み番号を再利用しない。
3. prefixを変更しても同一collectionの連番は共有する。
4. 複数Repositoryからの採番は必ず中央Allocatorを通す。
5. BucketルートREADMEのmanaged blockは手動編集しない。
6. `config/current.json` のversion番号も中央Allocatorで発行する。
7. Bucket routingが将来変わっても、採番はその時点の物理Bucket内の既存最大値から継続する。
