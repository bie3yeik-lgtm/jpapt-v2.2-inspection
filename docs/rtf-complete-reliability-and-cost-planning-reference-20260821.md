# RTF Benchmark 完成・再発防止・コスト抑制 計画参考資料

更新日: 2026-08-21
用途: 次回実装計画の正本参考資料
対象: GHCR、Dockerfile、RTF Resolver、HF Jobs、RunPod Pod、RTF Service Result Collection、
`asr-rtf-rank`、GitHub Actions

## 1. この資料の目的

これまでの要求、実Actions runの調査結果、実装上の失敗、Rust/Python/Actionsの責務分離、
コスト抑制策、今後のVSDD実装順を一つにまとめる。

この資料でいう「完成」は、workflowがsuccessで終わることではない。次の全段階が同じ
immutable identityで成立し、Rustの受入契約を通過し、accepted recordとしてrankingへ入力
できることを意味する。

```text
GHCR digest
 -> RTF Resolver
 -> dataset revision / materialized audio / fixture JSONL / manifest SHA
 -> provider image pull / container readiness
 -> content probe
 -> inference
 -> result/metrics publish
 -> provider receipt / diagnostics
 -> Rust Service Result validation
 -> benchmark-record
 -> Rust ranking
 -> ranking PR
```

## 2. 利用者要求の要約

これまでの要求は、以下の失敗を再発させず、HF/RunPodへ実行させるDockerfile/GHCRを
確実に運用できる実装を、Rustの静的契約とPythonの現実的な外部実行境界に分けて完成させる
ことである。

### 明示された問題

1. Dockerfileのファイル配置ミス
2. Docker image内の実行ファイル・entrypointのpermission error
3. Pythonの動的環境変数や入力値が空でも処理が進む問題
4. HF Jobs / RunPodのサービス仕様を十分に確認しないままadapterを実装した問題
5. 必要なGHCR imageを都度作成することによるbuild/publish/download時間と金銭コスト
6. OOMが予測できるbatchを起動し、不要なCUDA errorとGPU課金を発生させる問題
7. receiptやmetricsが生成されない失敗をgeneric errorへ潰し、原因調査材料を失う問題
8. `RTF Service Result Collection`がprovider lifecycle、metrics publish、result identityを
   十分に結合できていない問題
9. rankingがempty、duplicate、identity混在を十分に拒否しない問題

### 期待される実装姿勢

- 実Jobを起動する前に、Rustで拒否できる入力はすべて拒否する
- PythonはHF/RunPod SDK・CLI、Docker、NeMo/PyTorchなど外部仕様が避けられない境界に限定する
- Docker/GHCRは再利用可能なdigest identityを正本とし、実行ごとに再buildしない
- content probeをmetricsより先に実行し、失敗時にfull inferenceを開始しない
- OOM・illegal access・SSH未到達を同一providerで無条件retryしない
- `guarded` modeを既定にし、失敗後のbatchを課金付きで起動しない
- completed resultはRust validatorを通過した場合だけrankingへ進める
- external serviceのsuccess、local contract PASS、ranking PRを別証拠として扱う

## 3. 現在確認できている成功と失敗

### 成功している前段

- GHCR digestの発行・解決
- HF Resolverによるdataset revision固定
- materialized audioの生成
- fixture JSONLとmanifest SHAの生成
- GHCR publish後にRTF Resolverを連続実行するActions接続
- local Docker build
- HF/RunPod adapterのstatic/mock test
- Rust `asr-rtf-rank`のschema validation、deterministic sort、empty/duplicate/identity gate

### 実Actionsで確認された失敗

| 境界 | 状態 |
|---|---|
| HF Jobs T4 batch 1 | CUDA illegal memory access、exit code 134、receiptなし |
| HF Jobs T4 batch 8/32 | OOM、receiptなし |
| RunPod Pod | SSH port未割当、connection refused、Pod exited、Pod not found |
| Result/metrics | completed payload未成立 |
| accepted benchmark record | 未成立 |
| ranking PR | 未成立 |

Resolver successはprovider execution successを意味しない。またActions workflow successも、
completed metricsやaccepted rankingを意味しない。

参照:

- [RTF Benchmark実run証拠](./rtf-benchmark-action-run-evidence-20260821.md)
- [HF/RunPod provider実態調査](./rtf-provider-service-investigation-20260821.md)
- [provider result / ranking契約](./asr-rtf-rank-provider-result-contract-20260821.md)

## 4. 失敗を防ぐ責務分離

### Rustが正本にする処理

```text
schema validation
typed input validation
empty/null/unknown value rejection
revision/image/fixture/manifest identity
SHA-256 and immutable URI validation
provider stage and failure taxonomy
raw log classification
receipt and metrics binding
cost policy
ranking and exclusion diagnostics
fail-closed decision
```

Rustは、外部サービスに依存しない判断をすべて担当する。ActionsやPythonが同じ判定を
独自実装してはならない。

### Pythonが担当する処理

```text
HF Jobs SDK/CLI invocation and status/log/metrics API
RunPod API/CLI invocation and status/SSH/log diagnostics
Docker container runtime
NeMo/PyTorch GPU inference
Hugging Face Dataset upload
provider raw response preservation
```

Pythonは空の値を補完してはいけない。必須値は明示的にfailし、Rust validatorに渡せる
machine-readable envelopeを生成する。

### GitHub Actionsが担当する処理

```text
credential injection
workflow input dispatch
Rust CLI execution
provider adapter invocation
artifact upload
branch/PR publication
```

Actionsはruntime semantics、ranking判定、provider failure分類を独自定義しない。

## 5. Dockerfile / GHCR 再発防止契約

### Dockerfile build context

- `COPY`対象はrepository rootからの正規相対pathに固定する
- `.dockerignore`でtarget、cache、model、audio、datasetを除外する
- build前にDockerfileが参照する全pathの存在をstatic checkする
- Dockerfile内でcopy後のfile listを検証する
- entrypointは明示的に`chmod +x`し、`RUN bash -n`とPython compileを実行する
- `ENTRYPOINT`、working directory、runtime pathをstatic contractで確認する
- base image、runner version、source revision、roleをOCI labelへ保存する
- secret、HF token、RunPod token、model weight、fixture実体をlayerへ入れない

### Image再利用とGHCRコスト

- GHCR build/publishはsource revisionまたはDockerfile/requirements変更時だけ行う
- publish後のdigestをartifactへ保存し、後続Resolver/providerは同じdigestを使う
- tagをprovider inputへ渡さない
- build artifactのrole/source/digestをRustまたはstatic contractで検証する
- providerごと、batchごとにimageを再buildしない
- local Docker build、container import/version smoke、mock adapterを先に実行する
- GHCR remote publishはlocal contract PASS後にだけ行う

## 6. Pythonの空値・動的変数防止契約

### 必須値

次の値は空文字、null、floating revisionを許さない。

```text
RTF_RUN_ID
RTF_MODEL_ID
RTF_MODEL_REVISION
RTF_DATASET_ID
RTF_DATASET_REVISION
RTF_FIXTURE_REPO_ID
RTF_FIXTURE_REVISION
RTF_FIXTURE_MANIFEST_SHA256
RTF_IMAGE_DIGEST
RTF_GPU
RTF_BATCH_SIZE
RTF_PROVIDER
RTF_SERVICE_ID
```

### 実装ルール

- Python argparseでrequiredを付ける
- enum値はchoicesで制限する
- revisionは40-hex、imageは`sha256:<64-hex>`で検証する
- pathはabsolute/path traversal/emptyを拒否する
- environment variableは`os.environ.get(..., default)`で重要identityを補完しない
- JSON生成前に型検証し、Rust schema validationへ渡す
- receiptがない場合はsuccessを返さず、stage付きblocked envelopeを生成する
- logにtokenやsecretを出力しない

## 7. HF Jobs仕様前提の実装

HF JobsにはJob自身のtimeoutがあり、workflowの`timeout-minutes`とは別である。公式仕様では
default timeoutが30分で、`--timeout`、Job inspect、logs、metrics、cancelが提供されている。
そのため、次を必須化する。

- `hf jobs run`へ明示timeoutを渡す
- submit直後のJob ID/URLを保存する
- scheduling、startup、inference、publishを区別する
- failure時にもJob logsとresource metricsを回収する
- CUDA OOMとillegal memory accessを別error codeにする
- Jobが失敗したら無条件retryしない
- 同一run identityのJob重複を作らない
- Job cancel可能なcleanup pathを持つ

公式参照: [HF Jobs configuration](https://huggingface.co/docs/hub/en/jobs-configuration)、
[HF Jobs API](https://huggingface.co/docs/huggingface_hub/en/package_reference/jobs)

## 8. RunPod仕様前提の実装

RunPodではPod作成、GPU allocation、container start、SSH endpoint、TCP reachability、
推論実行が別段階である。Pod ID取得や`pod create --wait`成功だけでは推論成功ではない。

- create responseを保存する
- Pod state、container state、SSH infoを別々に保存する
- SSH port未割当、connection refused、Pod exited、Pod not foundを別分類する
- private GHCR imageではregistry credentialを明示する
- SSH実行前にcontainer logs/system logsを回収する
- 失敗時はdiagnosticを保存してからdeleteする
- 成功時もmetrics/receipt回収後ただちにdeleteする
- stopだけで終わらせず、不要Podはterminate/deleteする
- RunPodのPod runtime上限を設定する
- 同一run identityの重複Podを作成しない

RunPodは停止中もvolume storage料金が残るため、停止とterminateを同一視しない。[RunPod
Manage Pods](https://docs.runpod.io/pods/manage-pods)

## 9. OOM・不要CUDAエラー防止

### 実行前

- Rust cost policyでprovider/GPU/batch/repeat/sample/audio上限を検証する
- T4でbatch 8/32を自動的に起動しない
- content probeをfull metricsより先に実行する
- image/model/dataset downloadが成立しない場合はinferenceへ進まない
- image pull、fixture load、model load、content probeを別stageで記録する

### 実行中

- defaultは`guarded`
- batch 1が失敗したらbatch 8/32をskipする
- batch 8が失敗したらbatch 32をskipする
- OOM、illegal access、provider startup failure、SSH failureは同じproviderで自動retryしない
- explicit `full-matrix`だけ全batch診断を許可する
- skipped batchは`COST_GUARD_SKIPPED`として記録する

### 実行後

- receipt/metricsがないものをrankingへ渡さない
- GPU errorのない成功結果だけを性能値として扱う
- blocked recordは原因とidentityを保存する
- OOMを「測定値」や「遅いRTF」として集計しない

## 10. RTF Service Result Collection

Service Result Collectionはmetricsの単純変換ではない。次の三つを結合する受領境界である。

```text
provider lifecycle evidence
  + immutable metrics payload
  + collection workflow identity
  -> accepted or blocked service-result
```

completed受入には以下を要求する。

- provider execution evidence
- content probe completed
- metrics schema valid
- immutable metrics URI/revision
- result/metrics SHA一致
- run/model/dataset/fixture/manifest/image identity一致
- provider stageとremote identity
- CERとcostがranking要件を満たす

不足時は次のように保存する。

```text
status: blocked | not_verified
provider_stage: submit | scheduling | image_pull | startup | ssh_ready | inference | publish
error_code: typed provider-specific code
error_message: non-secret diagnostic
raw_artifact: log/CLI/API evidence pointer
```

`PROVIDER_EXECUTION_FAILED`だけへ集約せず、HF JobsとRunPodの異なる失敗を保持する。

## 11. Rust ranking契約

`asr-rtf-rank`をランキングの唯一の判定器とする。

- schema validでないrecordは拒否
- phase不一致を拒否
- model/dataset/fixture/manifest/image identity混在を拒否
- duplicate accepted run/service/GPU/batchを拒否
- `provider_execution_proof=true`を要求
- CER/cost欠落を除外
- accepted recordが0件なら非zero終了
- exclusion reasonをdiagnosticsへ保存
- deterministic sortを維持
- ActionsはRust出力からMarkdownとPRを生成するだけにする

ランキングPRは、accepted provider resultが存在する場合だけ作成する。blocked/not_verified
だけのworkflowはsuccessやPRへ昇格させない。

## 12. VSDD実装計画

### R0 — 契約とfixture

Rust schema、provider evidence、cost policy、completed/blocked/empty/OOM/SSH failure fixtureを
固定する。

### R1 — Rust validator

identity、SHA、revision、provider stage、receipt、metrics、content、cost policyをtypedに
検証する。

### R2 — Rust log classifier

redacted Actions logとprovider raw responseをRustで分類し、service-specific error codeを
生成する。

### P1 — Python adapter

HF/RunPod SDK・CLI、Docker、NeMo/PyTorch、raw evidence収集だけを実装する。empty valueの
補完、ranking、identity policyの再実装は禁止する。

### P2 — Docker/GHCR

path、permission、import、version、label、digest、locked dependency、secret exclusionを
local buildで検証する。remote publishは最後に行う。

### R3 — Service Result Collection

Python envelopeをRustで受理し、completed/blockedを確定する。metrics publish成功とprovider
inference成功を分離する。

### R4 — Ranking Actions

record収集、Rust ranker、diagnostics、Markdown、成果PRを接続する。empty rankingではPRを作らない。

### P3 — live acceptance

R0〜R4のlocal/contract証拠が揃った後、HF JobsとRunPodを別々に実行する。実行はdigest、
model revision、dataset revision、fixture revision、manifest SHAを固定し、費用とcleanupを
記録する。

## 13. 受入チェックリスト

## 13-A. 現在の実行優先順位

直近はタスク解消を優先し、ローカルで時間のかかる実Docker/GPU smokeを通常チェックから
外す。実装不備を早く潰すため、次だけを通常のチェック対象とする。

- Rust unit/contract、format、clippy
- schema/static contract
- shell syntax
- workflow YAML/static assertions
- HF/RunPod fake CLI mock
- cost policyのguarded/full-matrix拒否テスト
- `git diff --check`

次は保留する。

- `test-rtf-provider-adapters.sh --mode docker`
- 実Docker container import/version smoke
- GPU content probe smoke
- HF Job / RunPod Pod live execution

保留は未検証を意味し、成功扱いにはしない。Docker/GPU smokeはR0〜R4の契約修正後、
外部provider受入直前に一度だけ明示実行する。

### Docker/GHCR

- [ ] Dockerfileの全COPY pathが存在する
- [ ] entrypointが実行可能である
- [ ] container内Python compile/import/version smokeが通る
- [ ] secret、model、fixture、audioがimage layerにない
- [ ] image labelとdigestがsource revisionに一致する
- [ ] 同一digestをResolver/providerが使用する

### Python/provider

- [ ] required environmentが空でない
- [ ] revision/image/path/typeがPython入口で検証される
- [ ] HF timeoutが明示される
- [ ] RunPod state/SSH/log/cleanupが分離される
- [ ] provider raw evidenceが保存される
- [ ] OOM/illegal access/SSH failureが自動retryされない

### Rust

- [ ] schema validationが通る
- [ ] identity/SHA/revision不一致がfailする
- [ ] empty/duplicate/mixed rankingがfailする
- [ ] cost guardが実行前に通る
- [ ] provider-specific failure codeが決定的に分類される
- [ ] exclusion diagnosticsが生成される

### External acceptance

- [ ] HF Job ID、status、logs、metrics、cleanupが記録される
- [ ] RunPod Pod ID、state、container、SSH、logs、cleanupが記録される
- [ ] content probeがcompletedである
- [ ] metrics URI/SHAがreceiptと一致する
- [ ] benchmark recordがacceptedになる
- [ ] ranking PRがaccepted recordだけを含む

## 14. 完了判定と停止条件

次のいずれかが未達なら、RTF Full benchmark完了とは扱わない。

- Dockerfile/image local buildの失敗
- 必須値の空渡し
- immutable identityの欠落
- provider stage不明
- content probe未完了
- metrics/receipt欠落
- OOMまたはillegal accessを成功扱い
- accepted record 0件
- ranking diagnosticsなし
- cleanup未確認

commit、push、PR、HF/RunPod/GHCR remote mutationは、各Unitのacceptance evidenceを確認し、
明示承認を得るまで行わない。
