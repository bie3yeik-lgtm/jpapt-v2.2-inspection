# RunPod container log表示

## 目的

GitHub ActionsのRTF Benchmark Runで、RunPod Podのcontainer logを推論中に
表示し、image pull後のentrypoint、content probe、CUDA実行、receipt発行の
状況をActionsログから追跡できるようにする。

## 仕様根拠

RunPod Podにはcontainer log（アプリケーションのstdout）とsystem log（Pod
ライフサイクル）がある。今回の要求は推論処理の確認を目的とするため、Actions
では`runpodctl pod logs <pod-id> --source container --tail 100 --follow`を
使用する。system logは既存のreadiness diagnosticsとPod状態で扱う。

## 変更内容

- `scripts/run-benchmark.sh`
  - PodがSSH-readyになった直後にcontainer log streamを開始。
  - `RunPod container log:`接頭辞付きでActions標準出力へ表示。
  - `RTF_RUNPOD_CONTAINER_LOG_TAIL`で初期表示行数を制御。
  - benchmark完了、失敗、signal cleanupのいずれでもstreamを停止。
  - 古い`runpodctl`で`pod logs`が未提供の場合は警告のみとし、benchmarkを
    実行不能にしない。
- `.github/workflows/rtf-benchmark-run.yml`
  - Actions実行時のtail値を100行に固定。
- `.github/workflows/rtf-benchmark-contracts.yml`
  - container log command、source、follow、tail contractの存在を検証。
- `scripts/ci/test-rtf-provider-adapters.sh`
  - static contractにcontainer log displayの検証を追加。

## 安全性とコスト

- log streamはPod作成後にのみ開始し、追加Podや追加GPUを作成しない。
- streamはPod削除前に停止する。
- log API未対応のCLIでも本体のreceipt回収を妨げない。
- log内容はRunPodから返る外部出力であり、秘密情報を環境変数として追加出力
  しない。既存のGitHub Actions secret maskingにも依存するため、モデルや
  providerがtokenをstdoutへ出力しないことを別途要求する。

## 検証

- `bash -n scripts/run-benchmark.sh scripts/ci/test-rtf-provider-adapters.sh`
  - pass
- `bash scripts/ci/test-rtf-provider-adapters.sh --mode static`
  - pass
- `bash scripts/ci/test-rtf-provider-adapters.sh --mode mock`
  - provider adapter mockはpass。container log API自体は、現在のローカル
    `runpodctl`が旧版で`pod logs`未提供のため外部API未検証。

## 未検証事項と次の安全な作業

- PRマージ後のActions RunPod smokeで、実際の`runpodctl`最新版から
  `RunPod container log:`が出力されることを確認する。
- log streamが利用できない場合も、既存のSSH stdout receipt回収とPod cleanupが
  成功することを確認する。

