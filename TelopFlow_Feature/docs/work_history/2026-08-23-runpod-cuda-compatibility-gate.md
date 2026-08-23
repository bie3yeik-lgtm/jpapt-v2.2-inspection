# RunPod CUDA互換性ゲートの修正

## 目的

直近のRunPod実行で、コンテナログに次の失敗が記録された。

```text
The NVIDIA driver on your system is too old (found version 12040).
```

これはfixture、GHCR digest、container log取得の問題ではなく、RunPodが
選択したホストドライバとNeMo SpeechイメージのCUDAランタイムの不一致である。

## 公式仕様に基づく判断

- RunPod公式のPod管理ドキュメントは、ホストCUDAとコンテナCUDAの一致を要求し、
  CUDA Versionsによる互換マシンの絞り込みを案内している。
- NVIDIA公式NeMo Speechインストールドキュメントは、NeMo Speechの公式コンテナを
  NGCから利用する形を示している。
- NGCの`nemo-speech:26.07.00`メタデータはCUDA 13.2ベースを示す。

したがって、RunPod作成時に`--min-cuda-version 13.2`を必須の下限として渡す。
この値は`RTF_RUNPOD_MIN_CUDA_VERSION`で管理し、既定値とActions設定を一致させる。

参照:

- https://docs.runpod.io/pods/manage-pods
- https://docs.nvidia.com/nemo/speech/nightly/starthere/install.html
- https://catalog.ngc.nvidia.com/orgs/nvidia/-/containers/nemo-speech/26.07.00

## 変更内容

- `scripts/run-benchmark.sh`
  - `RTF_RUNPOD_MIN_CUDA_VERSION`を追加（既定`13.2`）。
  - `major.minor`形式を検証し、`runpodctl pod create --min-cuda-version`へ渡す。
  - HF/RunPodログのドライバ不整合を`PROVIDER_CUDA_DRIVER_INCOMPATIBLE`へ分類。
- `docker/rtf-benchmark/entrypoint.sh`
  - NeMo実行失敗時のドライバ不整合を同じ型付きエラーへ分類。
- `.github/workflows/rtf-benchmark-run.yml`
  - 実行時のCUDA下限を`13.2`に固定。
- 契約テストとREADMEを更新。

## 証拠

- 対象Actions run: `32627998231`
- GHCR image digest: `sha256:3ea1bc51ecbab7d5922cffb209f0e0323b9914ec1dedfb40cd82bace658abfc8`
- RunPod container log取得は成功し、NeMoのモデル復元直後にドライバ不整合を確認。
- fixture revisionとmanifest fingerprintは一致していた。

## 検証

この変更後に、以下を実行する。

```text
bash -n scripts/run-benchmark.sh
bash -n docker/rtf-benchmark/entrypoint.sh
bash scripts/ci/test-rtf-provider-adapters.sh
```

ActionsのRunPod再実行は有料外部状態を変更するため、静的・モック検証成功後に
明示的な検証runとして行う。再実行で同じドライバエラーが出た場合は、RunPodの
`--min-cuda-version`選択結果と実ホストのCUDA情報を記録し、結果をRTFスコアに昇格しない。

## 未検証事項・次の安全な単位

- `13.2`下限で対象GPUが実際に割り当てられることは未検証。
- HF Jobs側はサービスがイメージ環境を選ぶため、今回のRunPod作成ゲートは適用されない。
- 次の単位は、変更済みdigestをGHCRへ発行し、RunPod smokeを1バッチだけ再実行して、
  `RTF_CONTENT_PROBE`と`RTF_RESULT_RECEIPT`を確認すること。

## ロールバック

この変更はRunPod作成引数と失敗分類に限定され、過去のresultやfixtureを変更しない。
問題があれば変更コミットをrevertし、既存の実行禁止・fail-closed動作を維持する。
