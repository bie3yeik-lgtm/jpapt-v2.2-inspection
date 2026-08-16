# Hugging Face Bucket Initialization

## 目的

`.github/workflows/hf-bucket-init.yml` は、新規作成済みの Hugging Face Storage Bucket をこのrepositoryの運用レイアウトへ初期化するための手動 GitHub Actions workflow です。

初期化では入力値をそのまま信用しません。Release対象の Rust CLI `asr-eval` の `bucket-init` subcommand が Hugging Face Hub から対象Model Repoのmanifestと、解決済みimmutable revisionの `README.md` Model Cardを取得して照合します。

次のいずれかに該当した場合はBucketへ書き込みません。

- Bucket ID、Model Repo ID、confirmationが一致しない。
- `HF_TOKEN` がない。
- 対象Bucketが空ではない。
- Model Repoの指定revisionをimmutable commit SHAへ解決できない。
- Hub manifestとModel Cardのtask/libraryが一致しない。
- workflow入力と取得済みmanifest/Model Cardの値が一致しない。
- Model Cardの必須メタデータが欠落、複数値、または曖昧である。
- model configからarchitectureを一意に取得できない。
- Bucket sync planにupload以外のoperationが含まれる。
- 初期化予定ファイル数がrepository実装の期待値と一致しない。
- apply直前の再検証でBucket状態またはModel Repo revisionが変化した。

既存Bucketへ追記・修復するworkflowではありません。**空の新規Bucketだけ**を対象とします。

## 前提

GitHub repositoryのActions secretに、対象Bucketへ書き込み可能な `HF_TOKEN` を登録してください。

Hugging Face側ではBucket自体を先に作成します。workflowはBucketを新規作成せず、指定された既存の空Bucketを初期化します。

## GitHub Actionsからの実行

GitHubの `Actions` から `Initialize HF Bucket` を選択し、`Run workflow` を実行します。

必須入力は次のとおりです。

| input | 意味 | `kotoba-tech/kotoba-whisper-v2.0` の例 |
|---|---|---|
| `bucket_id` | 初期化対象Bucket | `gawohok7/ci-test` |
| `model_repo` | 初期化のsource-of-truthにするModel Repo | `kotoba-tech/kotoba-whisper-v2.0` |
| `model_revision` | 検証開始時のrevision。実際にはcommit SHAへ解決して固定する | `main` |
| `expected_task` | 期待するASR task | `automatic-speech-recognition` |
| `expected_library` | 期待するlibrary | `transformers` |
| `expected_language` | 期待する単一language | `ja` |
| `expected_license` | 期待するlicense | `apache-2.0` |
| `expected_architecture` | Hub model configの `model_type` | `whisper` |
| `profile_set` | このrepositoryで使用するASR runtime profile set | `whisper-autoregressive-v1` |
| `confirmation` | 誤操作防止用の完全一致文字列 | `gawohok7/ci-test:kotoba-tech/kotoba-whisper-v2.0` |

`confirmation` は必ず次の形式で完全一致させます。

```text
<bucket_id>:<model_repo>
```

今回の試験値は次のとおりです。

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

## 検証フロー

Rust CLIは概ね次の順序で処理します。

```text
workflow inputs
    ↓
input syntax / confirmation validation
    ↓
hf buckets info
    ↓
require empty Bucket
    ↓
hf models info <repo> --revision <revision>
    ↓
resolve immutable model commit SHA
    ↓
README.mdをresolved SHAから取得
    ↓
Model Card front matter + Hub manifest + model configを相互照合
    ↓
workflow expected_* valuesと完全一致検証
    ↓
初期ファイルをtemporary stagingへ生成
    ↓
hf buckets sync --plan
    ↓
upload-only / expected file countを検証
    ↓
Bucket空状態を再確認
    ↓
resolved SHAでModel metadataを再確認
    ↓
hf buckets sync --apply
    ↓
remote bucket-manifest.jsonを再取得してpost-verify
```

`model_revision=main` を指定しても、Bucket manifestへ保存するsource revisionは検証時にHubが返したimmutable commit SHAです。apply直前の再検証もそのSHAに対して行います。

## 初期化後のBucket

現在のinitializerは次の管理用ファイルを作成します。

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

Bucketに空directoryだけを作ることはできないため、各運用prefixは管理用 `README.md` でmaterializeします。

`bucket-manifest.json` には少なくとも次のprovenanceを保存します。

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

## Model Repoに要求されるModel Card metadata

initializerはModel Repoの `README.md` 先頭にあるYAML front matterを検証します。

実行に必要なModel Card metadataは次の4項目です。

- `license`
- `language`
- `pipeline_tag`
- `library_name`

このinitializerでは初期化対象を曖昧にしないため、これらは**各1値だけ**を要求します。特に `language` が複数値の場合は自動選択せず失敗します。

Whisper日本語ASR repoであれば、最低限次のようなModel Card front matterを想定します。

```yaml
---
license: apache-2.0
language:
  - ja
pipeline_tag: automatic-speech-recognition
library_name: transformers
---
```

同じ情報がHub manifestにも存在する場合、Model Cardだけを信用するのではなく相互一致を要求します。現在は `pipeline_tag` と `library_name` をHub API結果とModel Cardの双方から確認します。

architectureはModel Cardから入力させず、Hub model configの `config.model_type` から取得します。Whisperの場合は次の値を期待します。

```json
{
  "model_type": "whisper"
}
```

したがって、workflow入力に `expected_architecture=whisper` と書いただけでは初期化できません。実際のmodel configが `whisper` を返す必要があります。

## 不正入力の例

たとえば次はすべてfailします。

```text
bucket_id = gawohok7/ci-test
model_repo = kotoba-tech/kotoba-whisper-v2.0
expected_language = en
```

Model Cardが `ja` なら一致しないため、write前に停止します。

またconfirmationが次のように異なる場合も停止します。

```text
confirmation = gawohok7/ci-test:some-other/model
```

対象Bucketに1ファイルでも存在する場合も、既存内容を推測して継続せず停止します。

## CLIからの利用

GitHub Actionsが呼び出しているRelease CLI surfaceは次の形です。

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

`--apply` を付けない場合はstagingとsync planの検証までを実施し、Bucketへ反映しません。GitHub Actionsでは前段のRust test/release buildを通過した後に `--apply` を使用します。

## 運用上の注意

Hugging Face Storage Bucket自体はversioned repositoryではありません。このinitializerが作るprovenanceと、その後のcandidate/config/run用repository toolingによってwrite-once/immutable運用を強制します。

初期化済みBucketに対してこのworkflowを再実行して「整える」運用は行わないでください。再実行時にnon-empty Bucketとしてfailすることが期待動作です。既存Bucketのrepair/migrationは別の明示的な操作として扱います。
