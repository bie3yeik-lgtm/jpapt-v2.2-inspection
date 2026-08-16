# HF Bucket initialization

## 目的

`.github/workflows/hf-bucket-init.yml`は、新規作成済みのHugging Face Bucketをこのrepositoryの標準treeへ初期化するためのmanual workflowである。既存Bucketをrepair/reconcileするworkflowではない。

## 必須入力

workflow dispatchでは次をすべて入力する。

```text
bucket_id
model_repo
model_revision
expected_task
expected_library
expected_language
expected_license
expected_architecture
profile_set
confirmation
```

`confirmation`は次と完全一致する必要がある。

```text
<bucket_id>:<model_repo>
```

## 実E2E済み入力例

initializerの実Bucket E2Eは`gawohok7/ci-test`と`kotoba-tech/kotoba-whisper-v2.0`で確認している。

```text
bucket_id              gawohok7/ci-test
model_repo             kotoba-tech/kotoba-whisper-v2.0
model_revision         main
expected_task          automatic-speech-recognition
expected_library       transformers
expected_language      ja
expected_license       apache-2.0
expected_architecture  whisper
```

workflow内部で`main`をそのまま保存せず、Hub APIでimmutable model commitへ解決してからmanifestを固定する。

## Parakeetについて

`nvidia/parakeet-tdt_ctc-0.6b-ja`のModel Cardからは次を静的に確認できる。

```text
task      automatic-speech-recognition
library   nemo
language  ja
license   cc-by-4.0
dataset   reazon-research/reazonspeech
```

一方、現在のBucket initializerの`expected_architecture`はmodel config/manifest resolverが返す具体値との一致を要求する。NeMo repoに対するarchitecture resolutionを実E2Eで確認していないため、`parakeet`等の文字列を推測して入力例にはしない。

Parakeet用新規Bucketをinitializerで作る場合は、先にNeMo repoからarchitecture evidenceを取得できるようresolverを拡張し、その実値を使ってE2Eを追加する。現在のParakeet開発では既存`gawohok7/jpapt-v2.2-dev-bucket`を使う。

## Model Cardに要求するmetadata

Bucket initializerは入力をそのまま信用しない。対象repoのHub manifestとModel Cardを取得し、入力との一致を確認する。

Transformers系の標準front matter例:

```yaml
---
license: apache-2.0
language:
  - ja
pipeline_tag: automatic-speech-recognition
library_name: transformers
---
```

NeMo系Model Card例:

```yaml
---
license: cc-by-4.0
language:
  - ja
pipeline_tag: automatic-speech-recognition
library_name: nemo
---
```

複数languageや欠落metadataを曖昧に自動選択しない。必要な値が取得できない、入力と不一致、revisionが解決できない場合は初期化を行わない。

## 保守的初期化フロー

```text
workflow dispatch
  ↓
input/confirmation validation
  ↓
Rust test + release build
  ↓
model revisionをimmutable SHAへ解決
  ↓
Model Card / Hub manifest照合
  ↓
remote Bucket file listing
  ↓
1 fileでも存在 → reject
  ↓
local initialization tree生成
  ↓
hf buckets sync plan
  ↓
planが期待したupload-only集合か検査
  ↓
apply直前にremoteを再確認
  ↓
apply
  ↓
recursive remote listingでexact path集合を検査
  ↓
remote bucket-manifest.jsonを再読取
```

## `total_files`を正本にしない

実E2Eではupload直後に`hf buckets info.total_files=0`が返る一方、recursive listingでは期待した8ファイルが存在するケースを確認した。このためaggregate counterをpostflightの正本にしない。

remote状態の正本は以下で得る実file listingとする。

```bash
hf buckets list <bucket> -R --format json
```

空Bucketでは`[]`ではなくempty stdoutになる場合がある。Rust CLIはempty stdoutだけを0 filesとして扱い、非空invalid JSONを空扱いしない。

## 初期化直後のtree

```text
/
├── README.md
├── bucket-manifest.json
├── config/
│   ├── README.md
│   └── versions/
│       └── README.md
├── candidates/
│   └── README.md
├── experiments/
│   └── README.md
├── runs/
│   └── README.md
└── benchmarks/
    └── README.md
```

## CLI

GitHub Actions内部ではRelease対象Rust CLIを使う。

```bash
asr-eval bucket-init \
  --bucket-id <bucket> \
  --model-repo <repo> \
  --model-revision <revision> \
  --expected-task <task> \
  --expected-library <library> \
  --expected-language <language> \
  --expected-license <license> \
  --expected-architecture <architecture> \
  --profile-set <profile> \
  --confirmation <bucket>:<repo> \
  --apply
```

`--apply`なしは検証/plan用途とし、書込みを行わない。

## 再実行

initializerはidempotent reconcilerではない。成功後に同じBucketへ再実行するとnon-empty preflightで失敗するのが正常である。migration/repairが必要なら別workflow/commandを設計する。
