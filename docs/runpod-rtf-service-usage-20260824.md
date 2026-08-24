# RunPod RTF service check の使い方

RunPod GPUをRTF benchmarkで使う前に、GPU availabilityとCUDA要件を確認するための運用手順です。

対象workflowは`RunPod RTF service inventory`、`RTF Verification Select`、`RTF Benchmark Run`です。
RunPodの在庫は変動するため、過去のartifactや設定だけで現在の利用可能性を判断せず、実行時のlive checkを使用します。

## 1. 事前準備

Repository Settings → Secrets and variables → Actions → Secrets に`RUNPOD_TOKEN`を登録します。
これはRunPod CLIの認証、在庫取得、probe Podの作成・削除に使用します。tokenをworkflow input、ログ、summary、artifactへ出力しないでください。

対象GPU、RunPod GPU ID、cloud type、CUDA下限は[`.github/runpod-rtf-services.json`](../.github/runpod-rtf-services.json)で管理します。現在のCUDA下限は`13.0`です。

GPUを追加・削除する場合は、共有設定、`evaluation/manifests/rtf-phase1-matrix.json`、両RTF workflowのchoice options、contract testを同時に確認します。

## 2. 無課金のavailability確認

Actions画面で`RunPod RTF service inventory` → `Run workflow`を選び、`mode=inventory-only`で実行します。`gpu`と`image`は空欄で構いません。

このモードは`runpodctl gpu list --include-unavailable`だけを実行し、Podを作成しません。次を確認します。

- `available=true`
- `secure_cloud`または`community_cloud=true`
- `selectable=true`
- `cuda_requirement=13.0`

artifact `runpod-rtf-service-inventory-<run_id>`には、raw inventory、結合済みreport、ログ、実行時設定が保存されます。このモードは実ホストのCUDA実証ではありません。

## 3. 一台のCUDA probe

特定GPUを実Podで確認する場合は、`mode=probe-selected`と共有設定の論理GPU名（例:`a5000`）を指定します。`image`を空欄にするとGHCRからdigest-pinned benchmark imageを解決します。

自分でimageを指定する場合は、`ghcr.io/<owner>/<image>@sha256:<64桁のsha256>`形式にしてください。

probeは、在庫とcloud typeの確認、一時Podの作成、SSH readiness（最大1時間）、`nvidia-smi`、GPU名、CUDA Version（13.0以上）、`/dev/nvidia0`の確認、Pod削除を順に行います。Podには`--min-cuda-version 13.0`と24時間の安全終了期限を指定し、作成後も30秒ごとにPodの存在と状態を確認します。

RTF benchmark本体では、Podの作成後からmetrics・receiptの取得完了まで同じheartbeatを実行します。各heartbeatで`nvidia-smi`からGPU使用率、メモリ使用量、温度、電力を取得し、ECC/Xid等のGPUエラー情報も確認します。Pod消失・停止時には直前のGPU診断、コンテナログtail、Pod状態をActions logとprovider diagnosticsへ保存します。metrics出力が完了した場合、またはSSH、benchmark、APIの内部エラーが発生した場合は、終了処理でPodを削除します。作成・readiness・SSH情報取得・metrics取得に失敗した場合は、Actions logに終了コード、Pod ID、RunPod応答の要約を出力します。RunPod CLIの公式仕様には作成後の`--terminate-after`を延長する更新操作がないため、heartbeatはタイマーを延長するものではなく、長い安全期限と早期cleanupを組み合わせた監視です。

実GPUを借りるため短時間の料金が発生します。失敗時はartifactの`pod_id`と`cleanup_status`を必ず確認してください。

## 4. 全GPUのprobe

全対象GPUを確認する場合は`mode=probe-all`を指定します。GPUごとにPodを作成するため、通常は`inventory-only`または`probe-selected`を優先してください。一台でも失敗するとworkflowは失敗しますが、個別JSONはartifactに残ります。

## 5. RTF Verification Select

`RTF Verification Select`で`service_id=runpod-pod`を選ぶと、最新在庫、Phase 1 matrix、digest-pinned benchmark image、選択GPUのCUDA probeを順に確認し、probe成功後にselection artifactを発行します。

availabilityまたはCUDA probeが失敗した場合、selectionは成功しません。GitHub Actionsのchoice optionsは実行時に動的変更できないため、画面上の候補は静的ですが、実際の許可判定はlive gateで行います。

## 6. RTF Benchmark Run

`RTF Benchmark Run`を`provider=runpod`で実行すると、benchmark本体の前に同じGPUのprobeを実行します。probeが成功しなければRTF batchは開始しません。

推奨初回設定は`gpu=a5000`、`runpod_cloud_type=auto`、`inspection_profile=smoke`、`cost_mode=guarded`、`cuda_diagnostics=false`です。

`runpod_cloud_type=auto`ではSecure Cloudを優先し、なければCommunity Cloudを選択します。明示指定したcloudで利用できなければ失敗します。CUDA probe成功、benchmark receipt、metrics、ranking受入れは別の証拠であり、probe成功だけではASR品質やRTF結果を保証しません。

## 7. 判定とartifact

個別probe reportは[`runpod-cuda-probe.schema.json`](../evaluation/schemas/runpod-cuda-probe.schema.json)に従います。

| status | 意味 | 対応 |
| --- | --- | --- |
| `PASS` | availability、CUDA、GPU、probe、cleanupが成功 | RTF選択・実行へ進む |
| `FAIL` | 在庫、cloud、Pod、GPU名、CUDA、cleanupのいずれかが不合格 | failure codeを確認して再試行または対象変更 |
| `BLOCKED` | credentialやRunPod API等で判定不能 | secret・API・権限・ネットワークを確認 |

代表的なfailure codeは、`RUNPOD_GPU_NOT_AVAILABLE`（現在利用不可）、`RUNPOD_GPU_CLOUD_UNAVAILABLE`（指定cloudで利用不可）、`RUNPOD_CUDA_REQUIREMENT_UNSATISFIED`（CUDA下限不足）、`RUNPOD_NVIDIA_SMI_FAILED`（GPU診断失敗）、`RUNPOD_SSH_FAILED`（SSH timeout）、`RUNPOD_CLEANUP_FAILED`（Pod削除失敗）です。

## 8. ローカル検証

実RunPodを使わず、`bash scripts/ci/test-runpod-cuda-probe.sh`、`python -m py_compile scripts/ci/check-runpod-rtf-services.py`、`bash -n scripts/ci/run-runpod-cuda-probe.sh`、`python -m json.tool .github/runpod-rtf-services.json`、`python -m json.tool evaluation/schemas/runpod-cuda-probe.schema.json`を実行できます。

fixtureは実GPU availability、driver、料金、実Pod cleanupを証明しません。実サービスの証拠はActions artifactで確認します。

## 9. 失敗時の対応

1. artifactからprobe reportを取得し、`status`、`failure_code`、`pod_id`、`cleanup_status`を確認する。
2. `cleanup_status=FAIL`で`pod_id`がある場合、RunPod ConsoleまたはCLIでPodを確認して削除する。
3. `RUNPOD_GPU_NOT_AVAILABLE`ならinventory-onlyを再実行し、別GPUまたは時間を置いて再試行する。
4. CUDA失敗ではshared config、probe image digest、host driver、CUDA Versionを確認する。
5. 外部障害やcredential不足は成功結果としてrankingやpromotionへ進めない。

## 参照

- [RunPod runpodctl GPU command](https://docs.runpod.io/runpodctl/reference/runpodctl-gpu)
- [RunPod runpodctl Pod command](https://docs.runpod.io/runpodctl/reference/runpodctl-pod)
- [RunPod GraphQL manage Pods](https://docs.runpod.io/sdks/graphql/manage-pods)
- [GitHub Actions workflow_dispatch inputs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- [Recursive Delivery着手エントリー](./recursive-delivery-entry-runpod-cuda-availability-20260824.md)
