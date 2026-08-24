# RunPod RTF service inventory and selectable gate

この変更の目的は、RunPodをRTF benchmarkに使う前に、登録済みGPUが
benchmarkのCUDA要件を満たすスケジューラ条件で利用可能かを確認し、その結果を
GitHub Actionsの出力とartifactに残すことである。

## 実装

- `.github/runpod-rtf-services.json` がRunPod GPU ID、論理GPU名、CUDA下限、対象cloud
  typeの単一設定である。
- `.github/workflows/runpod-rtf-service-inventory.yml` は手動または6時間ごとに
  `runpodctl gpu list --include-unavailable --output json` を実行する。
- `scripts/ci/check-runpod-rtf-services.py` は設定と在庫を結合し、各GPUについて
  `available`、`secure_cloud`、`community_cloud`、`selectable`、CUDA下限をJSONで出力する。
- `.github/workflows/rtf-verification-select.yml` はRunPod選択時に同じ在庫検査を再実行し、
  現在利用できないGPUをRTF選択から拒否する。選択肢の静的なunionはGitHubの
  `workflow_dispatch`仕様上必要であり、実行時のlive gateが実際の許可判定となる。

CUDAバージョンはGPU一覧の属性として推測しない。RunPod公式のPod作成時
`--min-cuda-version`（GraphQLでは`allowedCudaVersions`）に設定値 `13.0` を渡す契約を
`cuda_requirement_status=enforced_at_pod_create` として記録する。inventory検査では
Podを作成しないため、課金やリソース予約は発生しない。実際のPod実行では既存の
`scripts/run-benchmark.sh` が同じCUDA下限をPod作成へ渡し、作成／起動失敗を別の実行結果として記録する。

## 権限と値の保存

`RUNPOD_TOKEN` は読み取り専用のRepository secretとして使用し、workflowやartifactへ
書き戻さない。GitHub Actionsからsecret値を永続化する必要はなく、非秘密の選択ポリシーは
`.github/runpod-rtf-services.json`にコミットする。現在availabilityは変動するため、環境変数や
コミット済みファイルに固定せず、各inventory／選択実行のartifactに観測結果を保存する。

## 参照資料

- [RunPod runpodctl overview](https://docs.runpod.io/runpodctl/overview)
- [RunPod GPU command](https://docs.runpod.io/runpodctl/reference/runpodctl-gpu)
- [RunPod Pod command](https://docs.runpod.io/runpodctl/reference/runpodctl-pod)
- [RunPod GraphQL: manage Pods](https://docs.runpod.io/sdks/graphql/manage-pods)
- [RunPod REST: create endpoint](https://docs.runpod.io/api-reference/endpoints/POST/endpoints)
- [GitHub Actions workflow_dispatch inputs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)

## 検証

ローカルでは実RunPod在庫を取得しないため、認証・外部サービス状態は未検証である。
JSON入力を用いた結合、Python構文、workflowの静的内容はCIで確認する。実際のavailability
判定はActions実行時のartifactを証拠とする。
