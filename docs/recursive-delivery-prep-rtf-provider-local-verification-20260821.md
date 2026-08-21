# Recursive delivery preparation: RTF provider local verification

更新日: 2026-08-21
対象branch: `codex/rtf-benchmark-completion-docs`

## 1. 目的と現在地

RTF BenchmarkをGitHub Actionsだけで確認する状態から、HF Jobs / RunPod adapter、
RTF benchmark Docker image、content/receipt回収経路をローカルで再現・検証できる状態へ
移行する。この文書は次の実装計画へ着手するための現状記録であり、外部providerの成功を
宣言する受入記録ではない。

現時点の依存関係は次のとおり。

```text
GHCR digest
  -> RTF Resolver
  -> dataset revision / fixture JSONL / manifest
  -> provider adapter (HF Jobs or RunPod)
  -> content probe
  -> result/metrics and receipt
  -> asr-rtf-rank
```

GHCR digest発行とRTF Resolverは実Actions runで成功している。未達なのは主にprovider
実行、失敗理由のサービス別収集、result/metrics到達性であり、Resolverを再実装することは
次の作業の前提にしない。

`RTF Service Result Collection`もこの依存グラフ上の独立した受領境界である。現行実装は
providerが渡したworkflow inputで`service-result.json`を組み立て、completed時だけHF上の
`metrics.json`を取得してrun/service/provider/environment等のidentityを照合する。したがって
service-resultはmetricsの単純な変換結果ではなく、次の三つを結合した成果物として扱う。

```text
provider lifecycle evidence
  + immutable metrics payload
  + workflow collection identity
  -> accepted or blocked service-result
```

## 2. authority、scope、非目標

### 正本

- `scripts/run-benchmark.sh`: provider hand-off、待機、artifact回収の実装
- `docker/rtf-benchmark/Dockerfile`: 実行イメージ
- `docker/rtf-benchmark/entrypoint.sh`: Job/Pod内の実行入口
- `evaluation/schemas/rtf-provider-content.schema.json`: content probeのmachine-readable契約
- `docs/rtf-benchmark-flow-and-actions-contract-20260821.md`: GHCR publishからResolverまでのActions契約
- `docs/asr-rtf-rank-provider-result-contract-20260821.md`: ranking入力のresult/metrics契約
- `docs/rtf-provider-service-investigation-20260821.md`: 実Actions runとprovider仕様の調査記録
- `docs/rtf-local-provider-adapter-test.md`: ローカル検証モードと外部作用の境界

### 今回の準備資料の範囲

- ローカルのstatic/mock/docker/live検証の到達範囲を記録する
- HF JobsとRunPodの失敗境界を分離する
- 次のrecursive units、型付きfailure、受入証拠を定義する
- GitHub Actionsでのmock contract testとの関係を固定する

### 非目標

- この文書だけでHF JobまたはRunPod Podを実行成功と扱うこと
- private GHCR、HF、RunPodの認証情報やremote stateを推測すること
- result/metrics未生成のrunをrankingへ流すこと
- DirectML経路を復活させること
- 既存の無関係なdirty worktree変更を整理・revertすること

## 3. 完了済みUnitと証拠

### Unit L0 — ローカル検証入口を固定

成果物:

- `scripts/ci/test-rtf-provider-adapters.sh`
- `docs/rtf-local-provider-adapter-test.md`
- `.github/workflows/rtf-benchmark-contracts.yml` のmock test step

モード契約:

| mode | 外部作用 | 検証対象 | 判定 |
|---|---|---|---|
| `static` | なし | shell/python syntax、schema、Dockerfile、adapter文字列 | PASS |
| `mock` | なし | fake HF/RunPod CLI、実wrapper、content/receipt回収 | PASS |
| `docker` | base image取得 | Dockerfileからlocal imageをbuild | PASS |
| `live` | Job/Pod作成、課金可能性あり | 実サービスのsubmitからexecutionまで | 未実行 |

`live`は`--allow-external`、digest固定image、必要credentialを要求し、既定では外部状態を
変更しない。

### Unit L1 — content-first収集境界

成果物:

- `docker/rtf-benchmark/benchmark-runner/benchmark_runner/content_probe.py`
- `evaluation/schemas/rtf-provider-content.schema.json`
- `docker/rtf-benchmark/entrypoint.sh`
- `scripts/run-benchmark.sh`

content probeをmetricsより先に実行し、推論結果の内容到達性を独立したartifactとして扱う。
receiptがない場合はblockedへ閉じるが、provider固有のremote evidenceが不足する問題は残る。

### Unit L2 — GHCR publishからResolverの連続実行

成果物:

- `.github/workflows/ghcr-build-publish.yml`
- `.github/workflows/rtf-resolver.yml`
- `docs/rtf-benchmark-flow-and-actions-contract-20260821.md`

GHCR publish後にdigest-pinned imageを後続Resolverへ渡す。tagを評価identityとして扱わず、
build artifactのpublish証拠とdigestを検証してからResolverを呼ぶ。

### Unit L3 — RTF Service Result Collectionの現状固定

現行の受領フローは次のとおり。

```text
HF Jobs / RunPod adapter
  -> run_id, service_id, status, job_id, URI/SHA, error input
  -> rtf-service-result.yml
  -> completed時のみHF fixture repoのmetrics.jsonをfetch
  -> metrics identityをworkflow inputと照合
  -> Rust service-result validation
  -> completed時のみbenchmark-record生成
```

確認できた契約:

- completedは`job_id`、result/metrics URI、SHA-256を要求する
- result URIとmetrics URI、result SHAとmetrics SHAは一致を要求する
- metrics URIはimmutableなHF fixture repository revisionに限定する
- `metrics.json`の`run_id`、service、provider、environment、GPU、batch、profileを照合する
- blocked/failed/not_verifiedはmetrics fetchなしでservice-resultを作成できる
- completed以外は`benchmark-record`生成とranking入力へ進めない

不足している契約:

- HF Job ID / RunPod Pod ID以外のremote lifecycle（submit、scheduling、container start、
  SSH ready、inference、publish）がservice-result schemaにない
- receiptがないprovider失敗時に、remote log、Pod state、exit reason、resource snapshotを
  collectionへ渡せない
- RunPodのmetricsはprovider内でHF Datasetへpublishされる前提であり、RunPod APIから直接
  metricsを取得する経路ではない。このpublish成功とRunPod推論成功を別証拠として保存する
  必要がある
- 現行の`metrics_uri`はHF fixture repositoryを正本とするため、HF credentialとHF commit
  revisionがcollectionの実行依存になる
- `rtf-service-result.schema.json`とmetrics/record schemaに、DirectML退役前のprovider値が
  残っている箇所があり、現行provider契約との整合を別途確認する

このUnitの受入条件は、metricsを取得できたことだけではない。provider lifecycle evidence、
metrics payload、collection identity、SHA-256が同じrunに結合され、失敗時にもprovider固有
stageを失わないことを要求する。

### 検証コマンドと実結果

```text
bash scripts/ci/test-rtf-provider-adapters.sh --mode static  -> PASS
bash scripts/ci/test-rtf-provider-adapters.sh --mode mock    -> PASS (HF, RunPod)
bash scripts/ci/test-rtf-provider-adapters.sh --mode docker  -> PASS
git diff --check                                           -> PASS
```

Docker buildではNeMo base imageの既存環境について、`nemo-automodel`が
`opencv-python-headless`を要求する依存関係warningが出た。現時点ではbuildとrunnerの
Python compileを阻害していないが、実provider execution前にruntime import/推論probeで
扱いを決める未解決事項である。

## 4. 外部providerの現状と証拠境界

### HF Jobs

実Actions runではJob起動後のT4推論で失敗した。

- batch 1: CUDA illegal memory access、exit code 134、receiptなし
- batch 8/32: T4 GPU memory不足によるOOM、receiptなし
- `hf jobs run`の基本引数形式より、timeout、Job identity、失敗時log/resource回収、batch
  admissibilityの不足が問題

### RunPod

実Actions runでは推論開始前のprovisioning/SSH境界で失敗した。

- SSH port未割当、割当後のconnection refused
- Pod exited、またはPod not found
- receiptなしで`PROVIDER_EXECUTION_FAILED`へ正規化
- Pod削除前のdiagnostic保存、container/image pull状態、private GHCR registry credential、
  SSH以外のdiagnostic経路が不足

### 受入に必要な区別

```text
local static/mock          = source and contract evidence
docker build               = image construction evidence
HF/RunPod live             = external service evidence
content probe              = output content evidence
result/metrics             = ranking input evidence
asr-rtf-rank PR            = downstream publication evidence
```

上位の証拠は下位の成功を自動的に意味しない。特にResolver成功はprovider推論成功を意味せず、
mock PASSはHF/RunPodの実行成功を意味しない。

## 5. 次のRecursive Units

### Unit P1 — 共通provider failure envelopeとservice-result受領契約

責務: receiptやmetricsの有無にかかわらず、provider固有identityと失敗段階を保存し、
`RTF Service Result Collection`がそれを受領してservice-resultへ反映できるようにする。

入力/出力契約:

```text
provider: hf | runpod
provider_stage: submit | scheduling | container_start | ssh_ready | inference | publish
remote_job_id / pod_id: required after provider accepts request
remote_status: provider-specific terminal state
remote_error_code / remote_error_message: structured failure
resource_snapshot: optional, never fabricated
```

metrics evidenceは別に次を保持する。

```text
metrics_uri: immutable HF revision URI
metrics_sha256: fetched payload SHA-256
metrics_identity: run/model/dataset/manifest/image/provider identity
publish_revision: provider内publish commit
```

受入証拠: schema、HF/RunPod mock、receiptなしのfailure fixture、metrics fetch failure fixture、
identity mismatch fixture、既存blocked envelopeとの互換性確認。`PROVIDER_EXECUTION_FAILED`だけ
に収束させない。

### Unit P2 — HF Jobs adapter hardening

- Job自身のtimeoutを明示し、workflow timeoutと整合させる
- submit直後にJob ID/URLを保存する
- terminal status、logs、metrics、GPU memory snapshotを回収する
- illegal access、OOM、timeout、missing receiptを別error codeへ分類する
- T4で許容するbatch setを事前probeまたはprofileで決める

受入証拠: fake CLI contract、timeout引数 assertion、failure fixture、可能なら外部Jobの
diagnostic artifact。実GPU受入は別証拠として記録する。

### Unit P3 — RunPod adapter hardening

- create response、Pod state、container state、SSH endpointを保存する
- Pod ready、container ready、SSH TCP reachableを別poll段階にする
- private GHCR image使用時のregistry credential入力を明示する
- cleanup前にdiagnostic artifactを保存する
- SSH不能時に「推論未実行」を明示し、API/log経路で診断を試みる

受入証拠: fake CLI contract、各state transition fixture、Pod exited/not-found/connection
refused fixture、cleanup後も残るlocal diagnostic artifact。

### Unit P4 — result/metrics accepted gate

- completed contentとmetricsを同じrun identityへbindする
- provider execution evidenceがない結果をranking入力にしない
- blocked envelopeを`asr-rtf-rank`へ流さない
- result SHA、manifest SHA、image digest、provider identityを保存する

受入証拠: complete/blocked/mismatched fingerprint fixtures、Rust/schema validation、
ranking input rejection test。

### Unit P5 — live provider acceptance

P1〜P4が閉じた後、credentialと外部実行承認を得て、HF JobsとRunPodを分けて実行する。
各providerについて、submit、resource readiness、content、metrics、receipt、cleanupを
個別に記録する。片方の成功をもう片方の成功へ一般化しない。

## 6. 着手条件とブロッカー

### 着手可能

- static/mock/dockerのローカル入口
- schemaとfixtureの追加
- provider adapterの共通failure envelope
- 外部作用なしのActions contract test

### 外部依存で未確認

- HF Jobの実timeout、terminal log/metrics取得の実証
- T4 batch policyとillegal memory accessの再現・原因分離
- RunPodの実Pod state/SSH/API diagnostics
- private GHCR pull用RunPod registry credential
- 実result/metrics生成と`asr-rtf-rank`のaccepted input

### 安全境界

live testは明示承認なしに実行しない。remote Pod/Jobは、失敗時のdiagnostic回収設計と
cleanup期限が確認できるまで量産しない。

## 7. 次回プランニングで確定する項目

1. P1で追加するschemaの正本とRust/Python責務
2. HF/RunPod各serviceのerror code catalog
3. local fixtureで再現するstate transition一覧
4. runtime dependency warningをrequirementsへ追加するか、NeMo boundaryで許容するか
5. P4のaccepted result identityとrank workflowへの受け渡し
6. live実行のcredential、予算、cleanup、成功判定

次の安全な着手単位は、外部providerを起動しない **Unit P1: 共通provider failure envelope**
である。

## 8. ロールバックと変更管理

新しいfailure envelopeとlocal testは既存candidate/result artifactを書き換えない。問題が
見つかった場合は新schema・adapter gateをfeature単位で無効化し、既存のblocked変換を保った
まま原因を記録する。commit、push、PR、HF/RunPod remote mutationは別途明示承認があるまで
行わない。
