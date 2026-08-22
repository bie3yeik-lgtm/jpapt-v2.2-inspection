# RTF provider service 実態調査

調査日: 2026-08-21
対象: HF Jobs / RunPod Pod provider execution
対象workflow: `.github/workflows/rtf-benchmark-run.yml`
関連実装: `scripts/run-benchmark.sh`, `docker/rtf-benchmark/entrypoint.sh`, `benchmark_runner`

## 結論

GHCR digestの解決、HF Resolverによるdataset revisionの固定、Resolverによるmaterialized audioとfixture JSONLの生成までは実runで成功している。一方、provider executionはサービスごとに異なる失敗が発生している。

| provider | 失敗境界 | 実runで確認された状態 |
|---|---|---|
| HF Jobs | Job起動後のGPU推論 | T4上でbatch 1がCUDA illegal memory access、batch 8/32がCUDA OOM |
| RunPod Pod | PodのSSH到達性・container lifecycle | SSH port未割当、port割当後のconnection refused、Pod exited、Pod not found |

現在の主問題はGHCR/Resolverではなく、provider adapterが各サービスの実行・待機・失敗収集・証拠保存仕様を十分に分離していないことである。

## 1. 成功している前段

### 1.1 RTF Resolver

[RTF Resolver run 32414089663](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32414089663) はsuccessで完了している。直近Benchmark Runに渡ったidentityは次のとおり。

```text
image_digest: sha256:317da2168f22a94a02b988060f0d13d759d745cced90560197963c6ddbebbaba
model_revision: 44edb27eea9317daf89333e75eb830db4b1cc298
dataset_revision: bf8819e8d9a5feb51b0c718686bd20ea67a3c729
fixture_repo_id: gawohok7/rtf-benchmark-fixtures
fixture_revision: 8d2c866ee315bdbed468b2e92e4587d85b6a5cc8
manifest_sha256: 9c47976f6101ebca1fc2575d46fde80d9a33dbc14b1e1f6dc2ca9aeb57a87694
```

このidentityがprovider runのログおよびblocked metrics envelopeにも保持されているため、今回のprovider失敗は前段のrevision解決失敗とは分類しない。

### 1.2 Benchmark Runの共通設計

`rtf-benchmark-run.yml`はbatch 1/8/32を順番に実行し、receiptが無い場合は次のsynthetic blocked envelopeを生成する。

```text
status: blocked
error_code: PROVIDER_EXECUTION_FAILED
error_message: provider execution did not produce a result receipt for batch <n>
```

このfail-closed動作は安全だが、provider固有の失敗理由をservice-resultへ渡さないため、HF JobsとRunPodの異なる失敗が同じerror codeに収束する。

## 2. HF Jobsの実態

### 2.1 実装された呼び出し

`scripts/run-benchmark.sh`は次の形でHF Jobsを起動する。

```text
hf jobs run --name <run-id> --flavor <t4-small|l4x1> \
  -e RTF_*=<value> ... \
  --secrets HF_TOKEN=<secret> \
  <digest-pinned-image> /opt/rtf-benchmark/entrypoint.sh --batch-size <n>
```

Hugging Faceの公式CLI仕様では、`hf jobs run IMAGE COMMAND...`、`--flavor`、`-e/--env`、`-s/--secrets`が利用でき、非detach実行はJob失敗時にnon-zeroを返す。今回のHF側エラーは、`hf jobs run`の基本的な引数形式よりも、Job内のCUDA推論とJob lifecycle/timeoutの扱いにある。

参照: [Hugging Face Jobs CLI](https://huggingface.co/docs/huggingface_hub/en/guides/cli)、[Hugging Face Jobs guide](https://huggingface.co/docs/huggingface_hub/guides/jobs)

### 2.2 実run

[RTF Benchmark Run 32414647326](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32414647326) は、Resolver identityを受け取った後、HF Jobs T4 laneで次の結果になった。

| batch | 実run結果 | 詳細 |
|---:|---|---|
| 1 | blocked | `CUDA error: an illegal memory access was encountered`。HF Jobはexit code 134でabortし、`RTF_RESULT_RECEIPT`を出力しなかった |
| 8 | blocked | 14.74 GiB GPUで1.53 GiB freeの状態から2.71 GiB allocationに失敗しOOM |
| 32 | blocked | 14.74 GiB GPUで2.48 GiB freeの状態から7.12 GiB allocationに失敗しOOM |

batch 8/32はT4の実メモリと可変長audio batchの組み合わせで説明可能なcapacity failureである。batch 1のillegal memory accessは単純なOOMとは分離し、CUDA/PyTorch/NeMo version、allocator状態、NeMo TDTのtranscribe実装、同一inputで再現する必要がある。

### 2.3 HF Jobs側の実装上の問題・不足

1. **Job timeoutを明示していない**。公式仕様ではJobのdefault timeoutは30分である。workflow jobのtimeout-minutesが180分でも、HF Job自身のtimeoutを延長するものではない。`hf jobs run --timeout ...`を明示し、workflow timeoutと整合させる必要がある。
2. **Job identityとresource metricsの取得が弱い**。Job IDはログ中のreceiptまたはCLI出力に依存している。Job URL/ID、final stage、resource metricsをmachine-readable envelopeへ保存する必要がある。公式Python APIには`inspect_job`、`fetch_job_logs`、`fetch_job_metrics`がある。
3. **推論abort時にremote evidenceを保存しない**。CUDA illegal accessのようにプロセス自体がabortするとJSONもreceiptも作れない。Job ID、last log cursor、failure stage、GPU memory snapshotをActions側で回収する設計が必要である。
4. **T4 laneのbatch policyが未分離**。batch 1/8/32を同じT4 flavorへ強制している。T4で成立するbatch setを事前probeし、unsupported/OOMをrankingへ流さないmatrix policyが必要である。

## 3. RunPod Podの実態

### 3.1 実装された呼び出し

`scripts/run-benchmark.sh`は次の順でPodを扱う。

```text
runpodctl pod create --image <digest-pinned-image> --gpu-id <mapped GPU name>
  --env <JSON> --docker-args 'sleep infinity' --ports 22/tcp
  --terminate-after <UTC DateTime>
-> runpodctl pod get <pod-id> --output json (readiness polling)
-> runpodctl ssh info <pod-id>
-> SSHで /opt/rtf-benchmark/entrypoint.sh を実行
-> SSHでmetricsとreceiptをcat
-> Pod delete
```

RunPod公式仕様でも`--image`、`--gpu-id`、`--env` JSON、`--docker-args`、`--ports`、`--terminate-after`がPod createの引数であり、SSH情報の取得は`runpodctl ssh info`で行う。実際にActionsで使用したrunpodctl v2.11.0は`--terminate-after`をGraphQLの`DateTime`として検証するため、既定2時間後のUTC timestampを渡す。`pod create --wait`の単一blocking呼出しは、Actions cancel時に`runpodctl`孤児プロセスとなり進捗も取得できなかったため廃止した。さらに、create自体もスケジューリング・image pull待ちで無出力のまま停止し得るため、`RTF_RUNPOD_CREATE_TIMEOUT_MINUTES`（既定20分）の独立上限を設け、`phase=pod_create`の経過ログを出す。create応答が戻らなくても、同じ一意run IDのPodがAPI一覧へ現れた場合はそのIDを採用してcreate待ちを解放し、`pod get` readinessへ進む。上限超過は`RUNPOD_POD_CREATE_TIMEOUT`として記録し、固有run IDでのPod検索・削除を行う。create成功後は`pod get`を`RTF_RUNPOD_POLL_SECONDS`（既定15秒）でpollし、`desiredStatus=RUNNING`かつ`runtime`存在を確認する。readiness全体は`RTF_RUNPOD_WAIT_TIMEOUT_MINUTES`（既定20分）で制限し、イメージ取得・起動を含むprovider側の準備時間を吸収する。

参照: [RunPod runpodctl pod reference](https://docs.runpod.io/runpodctl/reference/runpodctl-pod)

### 3.2 実run

[RTF Benchmark Run 32409761260](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32409761260)では、RunPod CLI doctorはhealthyだったが、Pod実行は推論開始前に停止した。

確認された状態:

- SSH portが長時間未割当
- port割当後も`connection refused`
- 10分のSSH待機timeout
- 別Podでは`pod is exited, so it will never become reachable`
- 別Podでは`pod is no longer listed`
- 3 batchすべてreceipt無し、`PROVIDER_EXECUTION_FAILED`へ正規化

このrunではNeMo推論ログ、CUDA OOM、metrics payloadは確認できない。RunPod失敗をHF JobsのOOMと同一原因にしてはならず、Pod provisioning/container startup/SSH readinessの失敗と分類する。

### 3.3 RunPod側の実装上の問題・不足

1. **Pod readyとSSH readyを別段階として扱っていない**。`pod create --wait`成功後もSSH portが未割当またはrefusedになる。Pod state、container state、SSH endpoint、TCP reachabilityを別々の状態としてreceiptへ保存する必要がある。
2. **失敗時のPod診断を削除前に保存していない**。現在はcreate/SSH失敗時にcleanupでPodを削除する。料金保護として削除は正しいが、削除前に`pod get`、create response、last state、image pull/container exit情報をActions artifactへ保存すべきである。
3. **private GHCR pullのcredential契約が明示されていない**。`pod create`に`--registry-auth-id`がない。private GHCR packageを使う場合はRunPod registry credentialを明示指定する必要があり、public visibilityに依存してはいけない。Pod作成成功はimage pullとcontainer起動の成功証拠ではない。
4. **SSH経由の実行を単一経路にしている**。SSH unavailable時には実行不能であり、Pod logs/API側のdiagnostic collectionを先に行うfallbackが必要である。

## 4. 共通result/receipt境界

`publish_result.py`はcompleted metricsだけをHF Datasetへuploadし、commit SHAをrevisionとしてURIへ埋め込む。blocked payloadではremote uploadを行わず、local receiptだけを出力する。この設計により未完了結果をrankingへ入れない点は正しい。

ただしreceiptには次のservice-specific evidenceが不足している。

```text
provider_stage: submit | scheduling | container_start | ssh_ready | inference | publish
remote_job_id / pod_id
remote_status
remote_error_code / remote_error_message
remote_log_uri or artifact pointer
resource_snapshot
```

現状はreceipt無しをworkflowが`PROVIDER_EXECUTION_FAILED`へ置き換えるため、上記情報が失われる。

## 5. 実装優先順位

### Unit A: provider-specific failure envelope

- HF Jobs / RunPod共通schemaへprovider stageとremote identityを追加
- receipt無しでもActions側でremote IDと失敗stageを保存
- `PROVIDER_EXECUTION_FAILED`をservice-specific codeへ分類

### Unit B: HF Jobs adapter

- `--timeout`を明示
- Job ID/URLを即時保存
- terminal stageとresource metricsを取得
- illegal accessとOOMを別error codeにする
- T4 batch admissibility probeを追加

### Unit C: RunPod adapter

- `pod create` responseと`pod get`をartifact化
- provisioning、container startup、SSH reachabilityを別pollにする
- private GHCR時のregistry-auth-idを設定入力にする
- 削除前にdiagnostic artifactを保存
- SSH不能時に推論未実行を明示する

### Unit D: accepted result gate

- provider execution proofはcompleted metricsとremote execution evidenceの両方を要求
- HF Jobs/RunPodのblocked envelopeをranking inputから除外
- provider-specific failureはFull移行条件へ伝播させない

## 6. 現時点の受入判定

| 境界 | 判定 |
|---|---|
| GHCR digest発行 | verified by workflow logs |
| HF dataset revision / Resolver | verified by Resolver run |
| fixture JSONL / manifest SHA | verified by Resolver output and downstream identity |
| HF Jobs submission | externally observed, but provider execution failed |
| HF Jobs T4 inference | blocked: illegal access/OOM |
| RunPod Pod creation | externally observed, but SSH/container readiness failed |
| RunPod inference | not verified; no SSH execution evidence |
| completed metrics/result URI | not verified |
| accepted benchmark record/ranking | blocked |

現段階で再実行すべき対象は、前段Resolverではなくprovider adapterである。再実行時も同じimage digest、model revision、dataset revision、fixture revision、manifest SHAを固定し、service-specific evidenceを失わないことを受入条件とする。
