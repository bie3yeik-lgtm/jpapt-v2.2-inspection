# Hugging Face Bucket Initialization

## 目的

`.github/workflows/hf-bucket-init.yml` は、新規作成済みの Hugging Face Storage Bucket をこのrepositoryの運用レイアウトへ初期化するための **手動専用** GitHub Actions workflow です。

最終workflowは `workflow_dispatch` だけをtriggerとします。push、schedule、PRから自動的にBucketを書き換える経路は持ちません。

初期化では入力値をそのまま信用しません。Release対象の Rust CLI `asr-eval` に追加した `bucket-init` subcommand が、Hugging Face Hub上のModel Repoと対象Bucketを実際に読み取り、入力値、Hub manifest、immutable revisionのModel Card、model config、Bucketの実ファイル一覧を相互検証した後にだけ書き込みます。

このworkflowは既存Bucketを「修復」「同期」「更新」するものではありません。**ファイルが1つも存在しない新規Bucketだけ**を対象にする、意図的に非idempotentなinitializerです。

## 前提

Hugging Face側でBucket自体を先に作成してください。このworkflowはBucketを新規作成しません。

GitHub repositoryのActions secretには、少なくとも対象Bucketを読み取り・書き込みできる `HF_TOKEN` を登録してください。workflow内ではtokenそのものを引数へ展開せず、`HF_TOKEN` 環境変数としてHugging Face CLIから使用します。

workflowでは `huggingface_hub==1.24.0` を固定して `hf` CLIを導入します。Bucket CLIの出力形式をRust側が検証するため、CLI versionを無制限に追従させない設計です。

## GitHub Actionsからの実行

GitHubの `Actions` から `Initialize HF Bucket` を選び、`Run workflow` を実行します。

すべての入力が必須です。

| input | 意味 | `kotoba-tech/kotoba-whisper-v2.0` の例 |
|---|---|---|
| `bucket_id` | 初期化対象Bucket。`namespace/name`形式 | `gawohok7/ci-test` |
| `model_repo` | 初期化provenanceのsourceとなるModel Repo | `kotoba-tech/kotoba-whisper-v2.0` |
| `model_revision` | 検証開始時のrevision。実行中にcommit SHAへ解決する | `main` |
| `expected_task` | 期待するASR task | `automatic-speech-recognition` |
| `expected_library` | 期待するlibrary | `transformers` |
| `expected_language` | 期待する単一language | `ja` |
| `expected_license` | 期待するlicense | `apache-2.0` |
| `expected_architecture` | Hub model configの`model_type` | `whisper` |
| `profile_set` | このrepositoryで使用するASR runtime profile set | `whisper-autoregressive-v1` |
| `confirmation` | 誤操作防止用の完全一致文字列 | `gawohok7/ci-test:kotoba-tech/kotoba-whisper-v2.0` |

`confirmation` は次の文字列と**完全一致**しなければなりません。

```text
<bucket_id>:<model_repo>
```

今回のintegration testでは次を使用しました。

```text
bucket_id             = gawohok7/ci-test
model_repo            = kotoba-tech/kotoba-whisper-v2.0
model_revision        = main
expected_task         = automatic-speech-recognition
expected_library      = transformers
expected_language     = ja
expected_license      = apache-2.0
expected_architecture = whisper
profile_set           = whisper-autoregressive-v1
confirmation          = gawohok7/ci-test:kotoba-tech/kotoba-whisper-v2.0
```

`gawohok7/ci-test` はintegration test用Bucketであり、productionのdefault値ではありません。

## workflowが実行するbuild gate

Bucket操作より前に、workflowはrepositoryのRust実装自体を検証します。

```text
cargo metadata --locked
cargo fmt --all -- --check
cargo test --locked -p asr-eval --no-default-features --features cpu
cargo build --locked --release -p asr-eval --no-default-features --features cpu
```

Bucket初期化には、この最後に生成されたRelease binary `target/release/asr-eval` を使用します。CI専用Python scriptなどで同じ処理を別実装していません。

## 保守的な検証フロー

Rust CLIは次の順序で処理します。

```text
workflow inputs
    ↓
Hub ID / non-empty / confirmation / HF_TOKEN validation
    ↓
hf buckets info <bucket>
    ↓
Bucket identityを確認
    ↓
hf buckets list <bucket> -R --format json
    ↓
実ファイル一覧が空であることを確認
    ↓
hf models info <repo> --revision <revision>
    ↓
指定revisionをimmutable model commit SHAへ解決
    ↓
README.mdをそのresolved SHAから取得
    ↓
Model Card front matterをstrict parse
    ↓
Hub manifest + Model Card + model configを相互照合
    ↓
workflow expected_* valuesと完全一致検証
    ↓
初期8ファイルをtemporary stagingへ生成
    ↓
hf buckets sync <staging> hf://buckets/<bucket> --plan <plan.jsonl>
    ↓
planが「8件・すべてupload」であることを検証
    ↓
Bucketの実ファイル一覧が依然空であることを再確認
    ↓
resolved SHAを指定してModel metadataを再取得・再検証
    ↓
hf buckets sync --apply <plan.jsonl>
    ↓
hf buckets list <bucket> -R --format json
    ↓
remote path集合が期待する8 pathと完全一致することを確認
    ↓
remote bucket-manifest.jsonを再取得
    ↓
typed BucketManifestとしてdeserializeし、provenance一致を確認
```

### なぜ `hf buckets info.total_files` を空判定の正本にしないのか

integration test中、upload自体は成功していたにもかかわらず、`hf buckets sync --apply` の直後に `hf buckets info` が一時的に `total_files=0` を返すケースを実際に観測しました。その後のrecursive listingでは8ファイルすべてが存在していました。

そのため最終実装では、`hf buckets info` は **Bucket IDが期待したBucketであることの確認**にだけ使用します。Bucketが空か、初期化後に何が存在するか、という安全判定にはaggregate counterを使いません。

実ファイル状態の正本は次です。

```bash
hf buckets list <bucket_id> -R --format json
```

さらに、空BucketではこのコマンドがJSONの`[]`ではなく**空stdout**を返すこともintegration testで確認しました。Rust実装は空白のみのstdoutを「0 files」として明示的に扱います。一方、非空stdoutが不正JSONなら空扱いにフォールバックせずfailします。

## Model Repo revisionの固定

`model_revision=main` のようなmutable revisionを入力しても、その文字列をそのままprovenanceとして信用しません。

最初の `hf models info` でHub commit SHAへ解決し、Model Cardの `README.md` もそのcommit SHAを指定して取得します。apply直前にはさらに、そのresolved SHAを明示指定してModel metadataを再取得します。

したがって、plan生成時とapply時の間に`main`が移動しても、別revisionを暗黙に初期化へ混入させません。

## Model Repoに要求されるModel Card metadata

initializerはModel Repoの `README.md` 先頭にあるYAML front matterを検証します。

execution-criticalな必須項目は次の4つです。

- `license`
- `language`
- `pipeline_tag`
- `library_name`

Whisper日本語ASR repoであれば、標準形は次です。

```yaml
---
license: apache-2.0
language:
  - ja
pipeline_tag: automatic-speech-recognition
library_name: transformers
---
```

### strict parserが要求すること

このinitializerはModel Card全体を汎用YAMLとして自由に解釈するのではなく、初期化に必要な4項目だけを保守的に読み取ります。

- `README.md` の先頭が `---` で始まること。
- front matterに閉じる `---` があること。
- 必須keyが欠落しないこと。
- 同じ必須keyを重複定義しないこと。
- execution-critical keyは各1値だけであること。
- `language` に複数言語がある場合、自動選択しないこと。
- critical fieldでnested YAMLを必要とする形を受理しないこと。
- `[ja, en]` のようなinline collectionから都合のよい値を選ばないこと。
- escapeを含む複雑なquoted scalarを推測して解釈しないこと。

たとえば次は拒否されます。

```yaml
language:
  - ja
  - en
```

同様に次もcritical metadataの表現として拒否されます。

```yaml
language: [ja]
```

単一値が必要な項目は、scalarまたは単一要素のblock listとして明示してください。

### Hub manifestとの相互照合

`pipeline_tag` と `library_name` はModel Cardだけを信用しません。`hf models info` のHub manifestが返したtask/libraryと、immutable Model Cardから取得した値の一致を要求します。

つまり、Model Cardだけを書き換えてHubが別task/libraryとして認識している状態は初期化できません。

### architectureの取得元

architectureはModel Cardの自由記述から取得しません。Hub model configの `config.model_type` を使用します。

Whisperなら次を要求します。

```json
{
  "model_type": "whisper"
}
```

したがってworkflowへ `expected_architecture=whisper` と入力しただけでは通りません。実際のHub model configが `whisper` を返す必要があります。

## 書き込み前に停止する条件

少なくとも次の場合、Bucketへapplyしません。

- `bucket_id` / `model_repo` が `namespace/name` 形式ではない。
- `confirmation` が `<bucket_id>:<model_repo>` と完全一致しない。
- `HF_TOKEN` がない。
- Bucketを取得できない、または返されたBucket IDが違う。
- recursive file listingに1ファイルでも存在する。
- Model revisionをimmutable hexadecimal commit SHAへ解決できない。
- Model Cardをresolved SHAから取得できない。
- Model Cardの必須metadataが欠落・重複・複数値・unsupported representationである。
- Hub manifestとModel Cardのtask/libraryが一致しない。
- `expected_*` と実際のmetadataが一致しない。
- model configからarchitectureを一意に取得できない。
- sync planにupload以外のactionがある。
- sync planのoperation数が8件ではない。
- plan後の再確認でBucketがnon-emptyになった。
- apply直前のimmutable model metadata再検証が失敗する。

この設計では「おそらく同じBucket」「既存READMEだけなら無視」「languageの先頭を採用」といった推測をしません。

## 初期化後のBucket

initializerは次の**8ファイルだけ**を初期配置します。

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

Bucketに空directoryだけをmaterializeするのではなく、各運用prefixへ管理用 `README.md` を配置します。

apply後のpostflightは単に「8ファイルある」ことだけを見ません。remote file path集合が次と**完全一致**することを要求します。

```text
README.md
benchmarks/README.md
bucket-manifest.json
candidates/README.md
config/README.md
config/versions/README.md
experiments/README.md
runs/README.md
```

不足だけでなく、未知の余計なpathが存在しても成功扱いしません。

## `bucket-manifest.json`

初期化時のsource identityを、Bucket rootの `bucket-manifest.json` へ保存します。

標準形は次です。

```json
{
  "schema_version": 1,
  "bucket_id": "gawohok7/ci-test",
  "initialized_at": "<RFC3339 timestamp>",
  "initialized_by": "<GitHub actor>",
  "profile_set": "whisper-autoregressive-v1",
  "source_model": {
    "repo_id": "kotoba-tech/kotoba-whisper-v2.0",
    "revision_requested": "main",
    "revision_resolved": "<immutable Hub commit SHA>",
    "task": "automatic-speech-recognition",
    "library": "transformers",
    "language": "ja",
    "license": "apache-2.0",
    "architecture": "whisper"
  }
}
```

`ModelManifest` と `BucketManifest` はRust側で `deny_unknown_fields` を使用します。postflightでremote manifestを読み戻す際も、未知フィールドを黙って無視しません。

## plan / applyの分離

Rust CLIはまずtemporary stagingを作り、Hugging Face CLIへsync planだけを生成させます。

```bash
hf buckets sync <staging> hf://buckets/<bucket_id> --plan <plan.jsonl>
```

Rust側でJSONLを読み、全operationが`upload`で、かつ8件であることを確認します。

条件を満たした場合に限り、`--apply`指定時は生成済みplanを適用します。

```bash
hf buckets sync --apply <plan.jsonl>
```

initializerはdeleteやoverwriteを前提とするsync planを許可しません。

## CLIからの利用

GitHub Actionsが呼び出すRelease CLI surfaceは次です。

```bash
asr-eval bucket-init \
  --bucket-id gawohok7/ci-test \
  --model-repo kotoba-tech/kotoba-whisper-v2.0 \
  --model-revision main \
  --expected-task automatic-speech-recognition \
  --expected-library transformers \
  --expected-language ja \
  --expected-license apache-2.0 \
  --expected-architecture whisper \
  --profile-set whisper-autoregressive-v1 \
  --confirmation gawohok7/ci-test:kotoba-tech/kotoba-whisper-v2.0 \
  --apply
```

`--apply` を付けない場合は、remote Bucketへ反映せず、manifest検証、staging生成、sync plan検証まで行います。

GitHub ActionsではRust unit testとRelease buildを通過した後に `--apply` を指定します。

## integration test evidence

最終実装は実際のHugging Face Bucketを使ってE2E検証しています。

- GitHub Actions workflow: `Initialize HF Bucket`
- successful run: `31946498867`
- source commit: `954118fab951a1f6ad4da206cb603cdf0c777518`
- test Bucket: `gawohok7/ci-test`
- Model Repo: `kotoba-tech/kotoba-whisper-v2.0`
- requested revision: `main`
- test時に解決されたrevision: `7eb575277d18909a4af8a24e3ae8cce2e99794ae`
- validated sync plan: `8 upload operations`
- Rust bucket-init unit tests: `7 passed`
- final Bucket postflight: SUCCESS

ここに書いたresolved SHAは**integration test時点の証拠**であり、将来の`main`に対する固定期待値ではありません。実運用では毎回指定revisionをHubから解決し、そのrunの`bucket-manifest.json`へimmutable SHAを記録します。

## 実試験で確認した重要なedge case

### 1. `hf models info`だけではModel Card metadataが十分とは限らない

初期実装ではHub info responseの`cardData.language`に依存しましたが、試験では必要なlanguageがそのresponseから取得できませんでした。

最終実装ではこれをfallbackで補いません。先にHub commit SHAを解決し、そのimmutable SHAの`README.md`自体を取得してModel Card front matterを検証します。

### 2. `hf buckets info.total_files`はapply直後の真実とは限らない

実試験ではapply成功直後にaggregate countが一時的に0を返しました。そのため最終実装はrecursive file listingへ変更しました。

### 3. 空Bucketのrecursive JSON listingは空stdoutになり得る

実試験で、空Bucketに対する`hf buckets list ... -R --format json`が空stdoutを返すことを確認しました。最終Rust実装ではこのケースだけを明示的にemptyとして受理し、その他のJSON decode failureは拒否します。

これらは「エラー時に緩く成功扱いする」ための例外ではなく、実際のCLI surfaceを観測した上で入力形を厳密に定義し直したものです。

## 再実行について

このinitializerは、同じBucketへ繰り返し実行して収束させるidempotent reconcilerではありません。

一度初期化すると8ファイルが存在するため、次回はpreflightのrecursive listingでnon-empty Bucketとして失敗します。これは期待動作です。

既存Bucketのrepair、migration、layout upgrade、manifest更新はこのworkflowへ混ぜず、別の明示的な操作として設計してください。

## Storage Bucketとimmutability

Hugging Face Storage Bucketはmutable storageです。このinitializer自体がBucketをversioned repositoryへ変換するわけではありません。

このrepositoryでは、初期化後のcandidate/config/runについて、中央Allocator、write-once prefix、strict candidate/runtime contract、promotion evidenceなど別のrepository toolingでimmutabilityを強制します。

Bucket初期化の責務は、その後の運用が開始できる**既知・空・検証済みsource provenanceを持つ初期状態**を作るところまでです。
