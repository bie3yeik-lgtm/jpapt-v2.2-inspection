# RunPod capacity selection and CUDA filter fix

## 目的

RunPodのWeb画面で空きGPUが見えているにもかかわらず、RTF Benchmark
ActionのPod作成が失敗する経路を修正する。

## 原因

- `scripts/run-benchmark.sh`が`--cloud-type SECURE`を固定していた。
  RunPodのGPU inventoryはSecure CloudとCommunity Cloudの可用性を別々に
  返すため、Community側だけに空きがある場合はWeb画面の空きとActionの
  作成条件が一致しない。
- `RTF_RUNPOD_MIN_CUDA_VERSION=13.2`を固定していた。RunPod公式のPod
  create仕様では許容CUDA値は列挙型で、現行ドキュメントの最大値は13.0。
  13.2は有効なスケジューリング条件ではない。

参照:

- https://docs.runpod.io/api-reference/pods/POST/pods
- https://docs.runpod.io/runpodctl/reference/runpodctl-pod
- https://docs.runpod.io/runpodctl/reference/runpodctl-gpu

## 修正

- `runpod_cloud_type` workflow inputを追加（`auto`/`SECURE`/`COMMUNITY`）。
- `auto`では`runpodctl gpu list --output json`を取得し、対象GPUの
  `available`、`secureCloud`、`communityCloud`を確認する。
- Secureが利用可能ならSecure、Secureが不可でCommunityが利用可能なら
  Communityを選択する。両方不可または在庫応答を解釈できない場合は、Podを
  作成せず`RUNPOD_GPU_NOT_AVAILABLE`で停止する。
- CUDA下限は`13.0`に固定する。使用するNeMo Speech 26.07系イメージは
  CUDA 13系を前提とするためである。RunPodの許容列挙値に合わせ、13.2を
  直接指定しない。Pod作成時にCUDA/driver条件で拒否された場合は
  `RUNPOD_CUDA_REQUIREMENT_UNSATISFIED`として記録する。
- 選択されたcloud type、GPU、CUDA条件をログに残す。
- Vast offer inventoryおよびVast benchmarkにも`cuda_max_good>=13.0`を追加し、
  作成直前にoffer IDを再検証する。

## 検証

- `bash -n scripts/run-benchmark.sh`: pass
- `bash -n scripts/run-vast-benchmark.sh`: pass
- `git diff --check`: pass
- provider実行はRunPodの在庫と資格情報に依存するため、Action再実行で確認する。

## 受入れ条件

- Communityのみ空きがあるGPUで`auto`がCommunityを選択する。
- Secureのみ空きがあるGPUで`auto`がSecureを選択する。
- CUDA下限`13.0`を`--min-cuda-version`で送信する。
- 両cloud tierに空きがない場合は課金Podを作成せず、診断可能なreceiptを出す。
