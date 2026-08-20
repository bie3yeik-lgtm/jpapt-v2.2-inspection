# RTF検証 GitHub Actions 利用手順

この文書は、RTF検証用GitHub Actionsを個別対象で起動し、実行結果を検証済み
artifactとして保存する手順を定義する。ベンチマークの仕様と受入れ境界は
[recursive-delivery-entry-rtf-score-20260820.md](recursive-delivery-entry-rtf-score-20260820.md)、
入力と比較条件は [Calculare-RTF-Score.md](Calculare-RTF-Score.md) を参照する。
環境別の詳細な実推論フローは [rtf-gpu-service-flow.md](rtf-gpu-service-flow.md) を参照する。

## 前提

- 対象ブランチのworkflowがGitHubへpush済みであること
- `run_id`は選択内容とGitHub Actionsのrun IDからworkflowが自動生成する
- 実測を行う場合は、固定dataset revision、materialized audio、固定benchmark image、
  providerの資格情報、GPU割当を別途準備すること
- credentials、model、audio、metricsの大きな成果物をGitへcommitしないこと

GitHub Actionsのworkflow選択画面から、次の順に実行する。

## 1. 個別対象を選択する

Workflow: **RTF Verification Select** (`rtf-verification-select.yml`)

`Run workflow`で次を一つずつ指定する。

| Input | 選択肢 |
|---|---|
| `service_id` | `hf-inference-endpoint`, `hf-jobs`, `runpod-pod`, `runpod-serverless` |
| `gpu` | `t4`, `l4`, `a5000`, `rtx3090`, `rtx4090` |
| `model_id` | Parakeet TDT/CTC, Kotoba Whisper |
| `dataset_id` | Common Voice 8, JSUT Basic5000, ReazonSpeech test |
| `decoder` | `tdt`, `ctc`, `whisper` |
| `batch_size` | `1`, `8`, `32` |

workflowは選択値をPhase 1 matrixと照合する。HF Jobsで存在しないGPUを選ぶなど、
無効な組合せは外部実行前に失敗する。成功時は
選択内容から生成された`run_id`を持つ`rtf-verification-selection-<run_id>` artifactに
`selection.json`が保存される。

## 2. 実行結果を保存・検証する

Workflow: **RTF Service Result Collection** (`rtf-service-result.yml`)

provider側でベンチマークを完了した後、次の値を指定して起動する。

- `run_id`: selection workflowと同じID
- `service_id`, `provider`, `environment`: 実行環境と一致させる
- `status`: 成功時は`completed`、実行不能時は`blocked`または`not_verified`
- `job_id`: provider側のjob identity
- `result_uri`, `result_sha256`: immutableな結果artifactのURIとSHA-256
- `metrics_uri`, `metrics_sha256`: metrics JSONのHTTPS URIとSHA-256

`metrics_uri`を指定するとworkflowがpayloadを取得し、次を実行する。

1. `metrics_sha256`とのSHA-256照合
2. `rtf-service-metrics.schema.json`によるschema検証
3. RTF、RTFx、dataset revision、manifest SHA-256、CER、VRAM、GPU utilization、料金の確認
4. `service-result.json`と`metrics.json`のartifact保存

`completed`では`job_id`、`result_uri`、`result_sha256`が必須である。実行できない場合に
架空の成功結果を登録せず、`error_code`と`error_message`を付けて`blocked`または
`not_verified`で保存する。

## 3. CLIからdispatchする場合

GitHub CLIの認証済み環境で、次のwrapperを使用できる。

```bash
GH_TOKEN="$GH_TOKEN" scripts/ci/dispatch-rtf-service-result.sh \
  OWNER/REPOSITORY \
  run-20260820-hf-l4-b1 \
  hf-jobs completed cuda linux \
  job-123 \
  https://example.invalid/result.json \
  RESULT_SHA256 \
  METRICS_SHA256 \
  https://example.invalid/metrics.json
```

このwrapperは既存のbounded dispatch helperを使用する。実際のprovider jobを起動する
ものではないため、provider側の実行とmetrics公開を先に完了させる。

## 4. 結果の扱い

結果は次の識別子を混同しない。

- `result_sha256`: provider結果artifactのハッシュ
- `metrics_sha256`: RTF metrics payloadのハッシュ
- `rtf_scope=model`: モデル入力後の推論時間
- `rtf_scope=service`: decode、resample、前処理、推論、後処理を含む時間

## リポジトリへの保存先

`RTF Service Result Collection`が正常に完了すると、Actionsは次の構造へ結果をcommitし、
`inspection/<run_id>-<service_id>`ブランチから`main`向けPRを作成する。これにより、
workflowを起動したブランチが保護されていても結果をリポジトリへ保存できる。

`RTF Verification Select`が生成するselection Artifactは、完了イベントを受けた
`Persist RTF Verification Artifacts` Workflowが回収する。このWorkflowはArtifact生成完了後に
起動し、`inspection/rtf-artifacts-<actions_run_id>`ブランチへまとめてcommitし、`main`向けPRを
作成する。Artifact回収はproviderのmetrics結果回収とは別経路である。
完了済みrunを再回収する場合は、このWorkflowを手動起動し、`run_id`に対象の
`RTF Verification Select` run IDを指定する。

```text
rtf-scores/
└── <run_id>/
    └── <service_id>/
        ├── service-result.json
        ├── metrics.json       # metrics_uriを指定した場合
        └── summary.md
```

`service-result.json`には外部GPUサービスの`job_id`、`result_uri`、provider、環境、
SHA-256が保存される。`metrics.json`には実推論のRTF/RTFx、CER、VRAM、GPU utilization、
料金など、providerが返した検証済みmetricsが保存される。外部result本体を取得できない
場合でも、URIとhashをenvelopeに残す。

workflowには`contents: write`と`pull-requests: write`権限が必要である。保存commitは
`chore: persist RTF score <run_id> <service_id>`という形式で作成される。同じrunを
再実行した場合は同名ブランチと既存PRを再利用する。

ランキングはcompletedかつ必要なmetricが存在するrecordだけを対象にする。GPU実行証拠、
CER、VRAM、料金が欠けているrecordを、推測でPASSや最安として扱わない。

## 現在の検証境界

workflow、schema、Rust/Python契約はローカル検証済みである。一方、HF/RunPodの実GPU実行、
固定音声のmaterialization、provider実行証拠、実metrics取得は外部資格情報とGPU割当が
必要であり、未検証の場合はworkflow上でも`blocked`/`not_verified`として記録する。
