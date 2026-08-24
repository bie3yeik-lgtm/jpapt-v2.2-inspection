# RunPod公式仕様照合とL4ラベル分離

## 目的

Actions run `32754281965` の誤判定を起点に、RunPod公式ドキュメントとRunPod CUDA probeおよびRTF Benchmark Actionsの契約を照合する。HF JobsのL4とRunPod PodのL4がActions画面上で同じ`l4`に見える問題も解消する。

## 公式仕様との照合結果

- RunPodのPod作成では正式なGPU type IDを指定する。Repositoryの`gpu_id`は`NVIDIA L4`などの正式IDを保持している。
- CUDA要件はPod作成時の`--min-cuda-version`でスケジューラへ渡す。13.0の要件はprobeとbenchmark本体の両方で維持する。
- `nvidia-smi`の表形式は列幅によりGPU名が省略されるため、正式名称の判定には`--query-gpu=name --format=csv,noheader`を使用する。
- `stockStatus=Low`は在庫が少ない状態であり、inventoryのavailable判定後でもPod create時の容量競合が起こり得る。既存のprobe側capacity retryはこの仕様に対応している。
- Podの公開状態は`RUNNING`、`EXITED`、`TERMINATED`を基準に扱い、SSH情報が取得できるまでPod存在確認を継続する。

参照:

- https://docs.runpod.io/runpodctl/reference/runpodctl-pod
- https://docs.runpod.io/api-reference/pods/POST/pods
- https://docs.runpod.io/api-reference/pods/GET/pods
- https://docs.runpod.io/sdks/graphql/manage-pods

## 変更内容

- `scripts/ci/run-runpod-cuda-probe.sh`
  - 表形式のGPU名ではなく、query形式の正式GPU名を厳密に検証する。
  - 判定失敗時にquery結果をログ出力する。
- `scripts/ci/test-runpod-cuda-probe.sh`
  - 表形式GPU名が省略されても正式名queryで通過するfixtureを追加した。
- `.github/workflows/rtf-benchmark-run.yml`
  - `hf-l4`と`runpod-l4`をActions選択肢として分離した。
  - 実行内部では両者をcanonical value`l4`へ正規化し、既存のprovider matrixを維持する。
  - `run-name`へproviderと選択ラベルを出力する。
- `.github/workflows/rtf-verification-select.yml`
  - 同じL4ラベル分離と正規化を適用した。
- `.github/workflows/rtf-benchmark-contracts.yml`
  - ラベル分離、正規化、run-nameを契約テストで固定した。
- `docs/rtf-github-actions-usage.md`
  - 利用者向けの選択方法を更新した。

## 検証

- `bash scripts/ci/test-runpod-cuda-probe.sh`: PASS
- `bash scripts/ci/test-rtf-provider-adapters.sh --mode static`: PASS
- `bash scripts/ci/test-rtf-provider-adapters.sh --mode mock`: PASS
- `bash -n scripts/ci/run-runpod-cuda-probe.sh scripts/ci/test-runpod-cuda-probe.sh scripts/run-benchmark.sh`: PASS
- 対象workflow 3ファイルのYAML parse: PASS
- `python -m py_compile scripts/ci/check-runpod-rtf-services.py`: PASS
- `git diff --check`: PASS

- RunPod CUDA probe fixture test
- Bash syntax check
- Workflow YAML/static contract check
- `git diff --check`

## 未検証事項

- RunPodの実GPUで全GPU typeを再実行する外部provider検証は、在庫とActions secretに依存するためローカルでは未検証。
- `runpod-l4`選択で実際にRunPod Podを作成し、HF L4と異なるservice_id付きreceiptが生成されることは次回Actions実行で確認する。

## 次の安全な作業

PRのcontract checks完了後、Actionsの`RTF Benchmark Run`で`provider=runpod,gpu=runpod-l4`または`provider=hf,gpu=hf-l4`を選択し、run-nameとreceiptのGPU/service_idを確認する。
