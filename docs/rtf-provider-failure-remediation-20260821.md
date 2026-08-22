# RTF provider failure remediation

確認日: 2026-08-21
対象: HF Jobs T4 smoke / GHCR publish後のRTF Resolver連続実行

## Confirmed failures

### HF Jobs

Job `6a87d1949cd058584adc4f4be` は、GHCR digest、model revision、fixture
revision、content probeまでは成功した。本測定のNeMo `transcribe()` 中に
`CUDA error: an illegal memory access was encountered` が発生し、metricsと
`RTF_RESULT_RECEIPT`を生成できなかった。

ログにはpinned allocator警告と、non-tarred datasetでのworker/tokenization警告も
存在した。これはCUDA illegal accessの直接原因と断定せず、再現時の診断対象とする。

### GHCR連続Resolver

Run `32445489921`では、GHCR build/publish、digest解決、image provenanceは成功した。
後続Resolverへ `inspection_profile: lough inspection` が渡され、Resolverの現行値
`smoke|pref|probe` に一致しないため `unknown inspection profile` で停止した。

## Implementation boundary

- benchmark batch `1/8/32`、fixture、model revision、digest identityは変更しない。
- NeMoのtyped `override_config` が利用できる場合は、そこへ
  `num_workers=0`、`pin_memory=false`、`use_lhotse=false` を設定する。
- NeMoが一時DataLoaderの `pin_memory=True` を内部固定する版にも対応するため、
  DataLoader生成境界で実効値を `num_workers=0`、`pin_memory=false`、
  `persistent_workers=false`、`prefetch_factor=None` に固定し、適用後の値を検証する。
- typed overrideを持たない旧APIでも `num_workers=0`、`use_lhotse=false` を渡し、
  同じDataLoader検証を行う。
- `RTF_CUDA_DIAGNOSTICS=1` のときだけ同期CUDA診断を有効にする。
- Jobがreceiptを出せず終了した場合も、provider failureをtyped receiptとして保存する。
- metricsがない失敗をcompletedとして公開しない。
- GHCR連続Resolverとrankingの古いprofile名を現行profileへ統一する。

Actions側の追加対策:

- `RTF Benchmark Run` はJob timeoutをGitHub Actions上限の360分へ拡張し、
  image/model/fixture取得を含む1/8/32直列実行を180分で打ち切らない。
- provider adapterへ `RTF_NUM_WORKERS` を渡さず、worker数・pinned memory・Lhotse利用は
  image内の固定policyだけを正本とする。
- provider実行前にdigest固定GHCR imageをpullし、`transcribe_compat.py` のloader safety
  policyをimage内部で検証する。ソース修正前の古いdigestを誤って実行しないためである。
- 既存のHF/RunPod receipt正規化、content gate、cost guard、Pod cleanupは維持する。

## Acceptance evidence

Static/unit evidence:

- `transcribe_compat`がtyped overrideと実DataLoaderの両方へ安全設定を適用する。
- unsupportedなNeMo引数を渡さない。
- hard-codedなNeMo temporary DataLoaderに対しても実効値を検証する。
- CUDA診断モードが同期設定を有効化する。
- illegal access/OOM/一般provider失敗を別error codeでreceipt化する。
- GHCR連続Resolverが`smoke`を渡す。

External evidence:

- 新digestを使ったHF T4 smokeでcontent probeと本測定を再確認する。
- completed時はmetrics URI/SHAとreceipt identityを確認する。
- 失敗時はJobが長時間待機せず、typed blocked receiptをResult Collectionへ渡す。
- 新GHCR digestでActionsのimage policy preflightが成功し、Jobログに
  `RTF_DATALOADER_POLICY={"num_workers":0,"pin_memory":false,"use_lhotse":false}` が出る。

## Remaining boundary

T4のbatch 8/32が物理的にOOMとなる場合、これはreceipt保証修正とは別のGPU容量制約で
あり、成功結果として扱わない。全batch完走には別GPUまたは明示的なmatrix policy変更が
必要である。

## 2026-08-23 Repository Secret 経由の再検証

対象run: [32593711141](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32593711141)

このrunはローカル`.env`をActionsへ渡さず、Repository Secretの`HF_TOKEN`をworkflowの`${{ secrets.HF_TOKEN }}`から`hf jobs run --secrets`へ伝達した。GHCR imageは次のimmutable digestで解決された。

```text
image_digest: sha256:9e697d44c6f969d50bd4c7cd3728a0806d7584be3d1525539b344c1c63ebaf08
model_revision: 44edb27eea9317daf89333e75eb830db4b1cc298
dataset_revision: bf8819e8d9a5feb51b0c718686bd20ea67a3c729
fixture_revision: 8d2c866ee315bdbed468b2e92e4587d85b6a5cc8
manifest_sha256: 9c47976f6101ebca1fc2575d46fde80d9a33dbc14b1e1f6dc2ca9aeb57a87694
```

HF Job `6a89f9577c5c7dd3792351f3`では、fixture JSONLと21音声の取得、モデル復元、content probe（`content_available=true`）まで成功した。その後、batch 1の全件推論開始時に`BENCHMARK_INFERENCE_FAILED` / CUDA illegal memory accessが発生し、metricsは生成されなかった。guarded cost policyによりbatch 8/32は`COST_GUARD_SKIPPED`となり、追加GPU費用を発生させず停止した。

ログ上、content probeは単独の`transcribe`呼出しで成功する一方、benchmark本体は同一NeMoモデルをwarmup・全件計測・repeatで再利用し、さらに本体だけautocastを有効にしていた。この実測差を原因候補として、次の修正を実装した。

- 本体の暗黙autocastを既定で無効化し、`RTF_ENABLE_AUTOCAST=1`の明示実験時だけ有効化する。
- warmupを廃止する。
- 各repeatでfixture済みsnapshotからNeMoモデルを再restoreし、推論後に破棄する。snapshot自体はHFキャッシュを使うため、再ダウンロードではない。
- GHCR cache exportは`mode=min`へ下げ、image push完了後に2.7GB級のbuild graph exportでworkflowが停滞しないようにする。

この修正後のHF/RunPod実GPU受入れは未確認であり、次の安全な単位は新digestを発行したうえで、同じHF T4 guarded batch 1を一度だけ再実行することである。

## 修正後のHF T4 guarded 実測

対象run: [32595956141](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32595956141)

新image digest `sha256:102087d0a70b2244865800604423e3089c0f872f81f98572faafbe2c914946bc`でRepository Secret経由のHF Jobを実行した。batch 1はcontent probe、全件推論、3 repeat、metrics upload、Rust benchmark record生成まで完了した。

```text
job_id: 6a8a03597c5c7dd3792352ca5
status: completed
batch_size: 1
rtfx: 95.26352914118695
rtf: 0.010497196660832634
processing_duration_sec: 56.71408616399998
peak_vram_bytes: 5606215680
metrics_sha256: 75ece9fc786fcc2afb8649057bde4a75e6f3f95f7234980c3d69ba9976ea0fe2
```

batch 8ではcontent probeは成功したが、本測定でT4の14.74 GiB中2.70 GiB freeの状態から2.71 GiB確保に失敗し、typed `BENCHMARK_INFERENCE_FAILED` / CUDA OOM receiptとなった。cost guardはbatch 32を`COST_GUARD_SKIPPED`として起動せず、追加費用を抑えた。これはbatch 1の再利用起因illegal accessとは別の、T4における長尺8件同時処理の容量制約である。

したがって現時点の受入れは、HF Secret境界、GHCR immutable image、fixture取得、content probe、batch 1 metrics/recordをcompleted、T4 batch 8/32を未成立として扱う。batch 8/32を成立させるには、別GPU lane、fixtureの長さ/バッチ契約見直し、または実効batchを変えないことを保証した長さ制御が必要であり、単純なOOM retryは行わない。

## RunPod guarded 実行境界

対象run: [32596969809](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32596969809)

Repository Secretの`RUNPOD_TOKEN`はworkflowから利用でき、`runpodctl doctor`は`healthy=true`、API key・API connectivity・SSH key同期の全てがpassした。したがってSecret権限とCLI設定は受入れ済みである。

一方、A5000 Podのbatch 1作成・接続・推論は約8分経過してもresult receiptを出力しなかったため、課金継続を避けてActionsをキャンセルした。collectにはbatch 1/8/32すべて`BENCHMARK_SETUP_FAILED`として保存され、RunPodの実GPU metricsやcontent probeは未取得である。RunPodの成功や失敗を推測せず、次回はPod create/SSH/image pullの個別時刻とremote receiptを取得できる観測を追加してから再試験する。

この観測改善として、Pod createの`--wait`を廃止し、create応答後の`runpodctl pod get` readiness pollingへ移行した。これによりPod ID取得、runtime準備、SSH接続の境界を分離し、Actionsキャンセル時に単一の長時間`runpodctl`呼出しを残さない。readiness timeoutやPod早期終了はtyped receiptとして保存する。

## RunPod Pod create の無出力ブロック対策

readiness pollingへ移行しても、`runpodctl pod create`自体がproviderのスケジューリングやimage pull待ちで応答しない場合は、Pod IDを取得する前にActionsが長時間拘束される。この境界を別の実行フェーズとして扱い、`RTF_RUNPOD_CREATE_TIMEOUT_MINUTES`（既定20分）で上限を設ける。create中は`phase=pod_create`と経過秒を定期出力し、上限超過を`RUNPOD_POD_CREATE_TIMEOUT`のblocked receiptへ変換する。

createプロセスを停止した場合でも、API側で要求が受理されていた可能性があるため、固有の`RTF_RUN_ID`でPod一覧を再検索し、孤児Podを削除する。`EXIT`だけではGitHub cancellation時のcleanupを保証できないため、`INT/TERM/HUP`を明示的に捕捉する。したがって、RunPodの再試験はこの上限・進捗・signal cleanupを含むimage/checkoutで一度だけ行い、create timeoutは推論失敗や容量不足と混同しない。

さらにworkflowにも`if: always() && inputs.provider == 'runpod'`のcleanup stepを設け、batch 1/8/32のrun IDを再検索して削除する。adapterのsignal trapがGitHub cancellationで実行されない場合も、job後段のcleanupで課金Podを回収する。

ローカルfake CLIでは、createを無出力ハングさせた状態を時間短縮して再現し、`RUNPOD_POD_CREATE_TIMEOUT`、exit status 124、receipt identity、外部resourceなしのcleanup経路を確認済みである。実RunPodではキャンセル後にrun IDのPodが稼働中で残る事象を検出し、Podを削除した。この事象を受け、signal cleanupとcreate前からの孤児Pod検索を追加した。これはRunPod APIの実availabilityやSSH到達性を証明するものではなく、adapterの停止契約に限定した証拠である。

## RunPod引数契約の修正

上記の未成立runを再試験する前に、`scripts/run-benchmark.sh`のRunPod引数を実CLIの契約へ合わせる。再試験では`--terminate-after`へ`2h`を渡したところ、runpodctl v2.11.0がGraphQL `DateTime`として検証し、Pod作成前に拒否した。このため、実装は既定2時間後のUTC timestampを渡す方式へ戻す。Podのreadiness待ちは既定20分の`RTF_RUNPOD_WAIT_TIMEOUT_MINUTES`として分離し、イメージpull・Pod起動・SSH準備の時間を含めて調整可能にした。既存の作成失敗時の名前検索、EXIT時delete、metrics/receipt回収後の即時deleteは維持する。

この変更はRepository Secretの利用方式を変更しない。GitHub Actionsでは`HF_TOKEN: ${{ secrets.HF_TOKEN }}`および`RUNPOD_TOKEN: ${{ secrets.RUNPOD_TOKEN }}`をworkflow stepのenvへ注入し、`run-benchmark.sh`へ渡す。ローカル`.env`やtoken値をActionsへコピーしない。次のRunPod guarded試験はこの引数修正を含むimageで一度だけ行い、Pod create、SSH接続、remote content probe、receipt、metrics URI/SHAを個別に確認する。

## RunPod DateTime修正後の再試験

対象run: [32598266646](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32598266646)

`runpodctl v2.11.0`のGraphQL `DateTime`拒否は解消し、Repository Secret、doctor、cost policy、digest-pinned image確認は通過した。しかしA5000 Pod作成時に次のprovider応答で停止した。

```text
There are no longer any instances available with the requested specifications.
```

したがって今回もremote content probe、metrics、result receiptは未取得であり、A5000のprovider容量不足によるblockedである。Pod作成応答は`RUNPOD_NO_INSTANCE_AVAILABLE`、`RUNPOD_TERMINATE_AFTER_INVALID`、`PROVIDER_RUNPOD_POD_CREATE_FAILED`へ分類したtyped receiptとして保存し、`BENCHMARK_SETUP_FAILED`へ情報を潰さない。別GPUまたは別時刻でのRunPod再試験が必要だが、同じA5000条件の無目的な再試行は行わない。

## RunPod L4 readiness polling 再試験

対象run: [32598836142](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32598836142)

L4ではRepository Secret、doctor、cost policy、digest-pinned image、Pod create開始まで進んだ。`pod create --wait`を除去した版をまだ含まない実行だったため、readiness中にreceiptを取得できず、8分経過時点でActionsをcancelした。Actionsログでは`runpodctl`が孤児プロセスとして終了し、content/metricsは未取得である。この結果を受け、現ブランチではcreate即時応答後の`pod get` pollingへ変更し、次回はreadiness timeout・pod state・cleanupを分離して検証する。

## 2026-08-23 RunPod CLI状態フィールド差分の実測

対象run: [32603917931](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32603917931)

修正版commit `5ee6ab9`でRunPod L4、`smoke`、`guarded`、batch 1から一度だけ再試験した。GHCR digest検証、RunPod CLI doctor、cost policy、Pod createは通過し、Pod `wqqtyh1vqhczy5`はAPIのlist応答で次の状態を示した。

```text
runtimeStatus: running
desiredStatus: RUNNING
runtimeStatusReason: null
```

しかしworkflowは`RUNPOD_READINESS_TIMEOUT`で停止し、content probe、metrics、result receiptは生成されなかった。原因はadapterが`runpodctl pod get`の`desiredStatus=RUNNING`かつ`runtime != null`だけをreadiness根拠にしていたことだった。実CLIの`pod list`では`runtimeStatus=RUNNING`が取得できるため、listとgetのJSON契約差分を吸収できていなかった。

この結果を受け、readiness pollingは次を行うよう修正した。

- `pod get`と、同一run IDの`pod list`を同時にpollする。
- `runtimeStatus`／`runtime_status`の`running`をreadinessとして扱う。
- `desiredStatus`／`desired_status`の`EXITED`・`TERMINATED`を終了として扱う。
- `sshCommand`／`ssh_command`の両方を受け入れる。

fake CLIでは、実測と同じくget側を`runtime=null`、list側を`runtimeStatus=RUNNING`にしたケースを追加し、static/mock検証はPASSした。実runのPodはworkflow cleanup後に一覧から消え、課金Podは残っていない。修正後のRunPod metrics取得は未成立であり、次の再試験はこのreadiness修正版がPR checksを通過した後に一度だけ行う。

## 2026-08-23 RunPod SSH port readiness の実測

`runtimeStatus=running`をreadinessとみなした次のrunでは、SSH接続が直後に`Connection refused`となった。これはPod lifecycleのrunningと、SSH server／port forwardingの受入れ可能状態が別であることを示す。したがって`runtimeStatus`だけではremote entrypointを開始してはならない。

adapterは次の追加gateを設けた。

- `runpodctl ssh info`から`sshCommand`／`ssh_command`を取得する。
- Pod lifecycleがrunningになった後、実SSH probeを行う。
- probeが成功するまでentrypointを実行しない。
- probeは`RTF_RUNPOD_SSH_PROBE_TIMEOUT_SECONDS`（既定10秒）でboundedにする。

この状態をfake CLIで再現したmockはPASSした。前回実runの証拠はPod作成・list runningまでで、metrics/resultは未成立である。SSH probe修正版がPR checksを通過するまでRunPodを再作成しない。

## 2026-08-23 SSH probe 修正版のRunPod実測

対象run: [32605824921](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32605824921)

SSH probeを含むcommit `2f0892a`でRunPod L4 guarded batch 1を再試験した。Podは`runtimeStatus=running`へ遷移したが、同一Podへの実SSH probeはexit code 255で、SSH endpointはまだ接続可能ではなかった。adapterはremote entrypointを起動せず、追加GPU処理を行わないままrunをcancelした。

```text
pod runtimeStatus: running
ssh probe: exit 255
batch 1: no content / no metrics / no result receipt
batch 8, 32: COST_GUARD_SKIPPED
cleanup: Pod list is empty after cancellation
```

このrunはRunPodのPod lifecycleとSSH readinessが別であることを確認した。実metrics未取得のため、RunPod laneは未成立のまま扱う。再試験する場合は同じPodを再利用せず、SSH port readinessのprovider側遅延またはimage/SSH service起動条件を別途解消してから、guarded batch 1を一度だけ実行する。

## RunPod imageのSSH daemon不足

SSH probeが255となる実行を受け、RTF imageを確認したところ、NeMo base imageを含め`openssh-server`がインストールされていなかった。`--docker-args 'sleep infinity'`はentrypointのkeepalive分岐を実行するだけで、SSH daemonを自動提供しないため、port 22を公開してもSSH接続は成立しない。

修正として、RTF imageへ`openssh-server`を追加し、entrypointの`sleep infinity`分岐で`ssh-keygen -A`と`/usr/sbin/sshd`をruntime起動する。host keyはimage layerへ焼き込まず、private keyをimageへ含めない。`sshd`が存在しない場合はkeepaliveをfail closedにする。次のRunPod試験はこのimageをGHCRへpublishし、発行されたdigestを使ってguarded batch 1を一度だけ実行する。
