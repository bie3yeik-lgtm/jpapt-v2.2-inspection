# RTF Rust契約・Python provider実行 実装方針

更新日: 2026-08-21
状態: 実装方針・VSDD着手資料
対象: `benchmark-ranking.yml`、RTF Service Result Collection、HF Jobs、RunPod Pod、GHCR image

## 1. 方針

RTF Benchmarkの正しい実装単位を、次の責務境界で固定する。

```text
Rust
  schema / identity / revision / SHA / failure taxonomy
  log parsing / receipt validation / ranking / fail-closed policy

Python
  HF Jobs API/CLI boundary
  RunPod API/CLI boundary
  Docker image runtime and NeMo/PyTorch execution
  provider-specific log and resource collection

GitHub Actions
  credentials / job orchestration / artifact upload / PR publication
```

Rustで表現できる契約・検証・ログ分類をActionsやPythonへ重複実装しない。HF/RunPodの
SDK、CLI、Docker、NeMo/PyTorchなど外部仕様に直接依存する処理はPythonへ限定し、必ず
Rustのmachine-readable contractを出力境界に置く。

providerコストは、実行前にRustが上限とmatrix modeを検証する。通常は`guarded` modeで
batch 1から開始し、失敗後のbatchを起動しない。全batchを診断目的で起動する場合だけ
`full-matrix`と明示承認を指定する。

HF Jobsは既定timeoutが30分で、公式CLI/APIにtimeout、cancel、inspect、logs、metricsが
あるため、workflow timeoutだけに依存せずJob自身へ`--timeout`を渡す。RunPodはstop中も
volume storageが課金され、不要なPodはterminateが必要なため、成功・失敗の両方でdeleteを
保証し、作成前後のdiagnosticを保存する。

参照: [HF Jobs configuration](https://huggingface.co/docs/hub/en/jobs-configuration)、
[HF Jobs API](https://huggingface.co/docs/huggingface_hub/en/package_reference/jobs)、
[RunPod Manage Pods](https://docs.runpod.io/pods/manage-pods)

## 2. 後戻りを防ぐ不変条件

- Rustが受理しないprovider resultをrankingへ渡さない
- PythonはRust schemaを変更・緩和しない
- Docker imageにはtoken、fixture実体、model重み、mutable tagを含めない
- GHCR imageはdigestでのみproviderへ渡す
- HF/RunPodのremote成功と、metrics publish成功を別evidenceとして保存する
- receiptがない失敗をgeneric errorだけへ潰さない
- content probe、metrics、result receipt、provider execution proofのrun identityを一致させる
- empty、duplicate、mixed revision、phase mismatchのrankingはRustで失敗させる
- DirectMLはactive routeに戻さない

## 3. VSDD実装順

### Unit R0 — 現行契約の固定

対象:

- `evaluation/schemas/rtf-service-result.schema.json`
- `evaluation/schemas/rtf-service-metrics.schema.json`
- `evaluation/schemas/rtf-benchmark-record.schema.json`
- `evaluation/schemas/rtf-provider-content.schema.json`
- `docs/asr-rtf-rank-provider-result-contract-20260821.md`

証明:

- schemaのrequired/additionalProperties確認
- DirectML値がactive contractへ混入していないことを確認
- completed/blocked/not_verified fixtureを準備
- run、image、fixture、manifest、metrics SHAの不一致fixtureを準備

完了条件: schemaがPython/Actionsの期待入力を先に規定し、未定義fieldを実装が勝手に
受理しない。

### Unit R1 — Rust typed provider evidence

Rustへ次の型境界を追加または確定する。

```text
ProviderStage
RemoteExecutionEvidence
MetricsPublicationEvidence
ContentProbeEvidence
ServiceResultEnvelope
```

検証責務:

- provider/service/environmentの整合
- stage遷移の妥当性
- remote job/pod identityの存在
- image、model、dataset、fixture、manifest identity
- metrics URI/revision/SHA
- content probe完了
- completed時のexecution proof

証明: Rust unit/integration test、invalid fixture全fail、canonical JSON hashの再現性。

cost policyもこのUnitの契約に含める。現在のRust CLIはprovider/GPU、batch、repeat、
sample count、audio target、duration上限を検証し、`full-matrix`には明示承認を要求する。

### Unit R2 — Rust log parser / failure taxonomy

HF JobsとRunPodのログ・CLI出力を、Python adapterが保存したraw evidenceからRustで分類する。

```text
HF: submit / scheduling / image_pull / startup / inference / publish / timeout
RunPod: create / provisioning / image_pull / container_start / ssh_ready / inference / publish
```

CUDA illegal memory access、OOM、timeout、SSH未到達、Pod exited、Pod not found、metrics
publish失敗をdistinct error codeへ分類する。ログに存在しない事実は推測せず、
`not_verified`または`diagnostic_missing`とする。

証明: 実Actions logから抽出したredacted fixture、各分類のnegative/positive test。

### Unit P1 — Python provider adapter

Pythonはprovider仕様に合わせて次だけを担当する。

- HF Jobs submit/status/log/metrics API呼び出し
- RunPod create/status/SSH/API diagnostics
- Docker image起動とNeMo/PyTorch inference
- raw log、CLI response、resource snapshotの保存
- Rust validatorへ渡すJSON envelopeの生成

Python adapterはranking、identity cross-check、error policyを実装しない。

証明:

- fake HF/RunPod CLI mock
- Docker local build
- provider-specific response fixture
- timeout、OOM、SSH failure、missing receiptの再現
- Rust validatorへの入力がschema validになること

adapterの外部実行には次のcost guardを必須にする。

- HF Job timeoutを`2h`で明示し、失敗時はJob IDを使ってcancel/diagnostic取得する
- RunPodは最大実行期限を`2h`にし、EXIT cleanupでPodをdeleteする
- image/model/dataset download失敗を推論retryとして再実行しない
- CUDA OOM/illegal access/SSH未到達は同じproviderで自動retryしない
- 同一run identityの重複Job/Podを作成しない

### Unit P2 — Docker/GHCR image

Dockerfileの責務:

- digest-pinned base image
- locked Python dependencies
- entrypointとcontent probe
- runtime version/build metadata label
- secretをlayerへ残さない
- startup/import/CLI smoke test

GHCR workflowの責務:

- build provenanceとimage digestの発行
- image role/source/revisionの検証
- digest-pinned referenceのResolver/providerへの伝達

証明: まずcontainer path/permission/importのstatic contractとmockを通し、local Docker build、
container import/version smokeは外部provider受入直前に明示実行する。GHCR build artifact
schemaとdigest identity static testは通常チェックで維持する。実GHCR publishはexternal
evidenceとして別記録する。

image側では、依存関係を毎回remoteで解決せずlocked requirementsを使用し、モデル・fixture
をimage layerへ焼き込まない。content probeをfull metricsより先に実行し、失敗時はGPU時間を
追加消費しない。

### Unit R3 — Rust Service Result Collection validator

`RTF Service Result Collection`はPython adapterのJSONをRustで検証する。

completed受入:

```text
provider execution evidence
  + content completed
  + metrics schema valid
  + metrics immutable URI/revision
  + result/metrics SHA一致
  + run/model/dataset/fixture/manifest/image identity一致
  -> benchmark-record accepted
```

不足時:

```text
blocked/not_verified
  + provider stage
  + error code
  + raw diagnostic artifact pointer
  -> ranking除外、原因は保存
```

### Unit R4 — Rust rankingとActions publication

`asr-rtf-rank`をrankingの唯一の判定器とする。Actionsはrecord収集、Rust CLI呼び出し、
Markdown整形、artifact/PR publicationだけを行う。

証明:

- phase1/full mapping
- empty/duplicate/mixed identity rejection
- exclusion diagnostics出力
- deterministic sort
- accepted recordのみMarkdown/PRへ出力

### Unit P3 — 外部provider受入

R0〜R4のlocal/contract evidenceが揃った後にのみ、HF JobsとRunPodを別々に実行する。
providerごとに次を記録する。

```text
submit -> allocation -> image pull -> container ready -> content probe
-> inference -> metrics publish -> receipt fetch -> Rust acceptance -> cleanup
```

一方のprovider成功を他方へ一般化しない。外部実行の結果が未検証ならranking PRを作らない。

## 4. 現行実装との接続

### 既にRustへ接続済み

- `asr-rtf-rank`のschema validation、sort、phase、identity、duplicate、empty gate
- `rtf-scores/ranking-exclusions.json`の出力
- Rust contract tests、format、clippy

### Pythonへ残すべきもの

- `docker/rtf-benchmark/benchmark_runner/*`
- HF Jobs / RunPodのprovider hand-off
- NeMo/PyTorch/ONNX Runtime GPU inference
- HF Datasetへのmetrics publish
- provider raw log/resource取得

### Actionsへ残すべきもの

- secret injection
- workflow timeoutとjob orchestration
- artifact upload
- inspection branch / PR publication

## 5. 現在のブロッカー

- HF T4 batch 1のillegal memory access原因未分離
- HF T4 batch 8/32のOOM policy未確定
- RunPod provisioning/container/SSH stateの実証不足
- private GHCR pull用registry credential契約未確定
- provider-specific evidenceをservice-resultへ保存するschema未完成
- 実completed metricsがないため、ランキングのexternal acceptance未成立

## 6. 受入判定

次の証拠レベルを混同しない。

| evidence | 意味 |
|---|---|
| Rust unit/contract | 契約とfail-closed判定が正しい |
| Python mock | provider adapterのhand-offが再現可能 |
| Docker build | imageを構築可能 |
| GHCR digest | remote image identityが固定された |
| HF/RunPod live | provider service上の実行状態 |
| metrics/receipt | resultを受領可能 |
| ranking PR | accepted recordの公開成果 |

Full benchmark完了は、最後の三段階が同一run identityで成立した場合だけとする。

## 7. 次の安全な実装単位

外部Jobを作成せずに実施する、**Unit R0/R1: provider evidence schemaとRust validatorの
fixtures追加**から開始する。その後、Python adapterのraw evidenceをRust validatorへ
接続し、最後にlive providerを実行する。

commit、push、PR、HF/RunPod/GHCR remote mutationは、各unitのacceptance evidenceを確認し、
別途明示承認を得るまで行わない。
