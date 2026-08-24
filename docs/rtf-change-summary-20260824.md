# RTF Benchmark変更総括・PR受入資料

## 目的

このPRは、RTF Benchmarkのprovider実行経路、結果契約、ランキング入力、Vast offer調査、CPU専用測定を同一のrevision-pinned運用へまとめる。GPU実行だけを成功条件にせず、外部実行がblockedになった場合も理由・identity・cleanup結果をreceiptとして残す。

## 変更範囲

### GPU / Vast

- RunPod GPU matrixにA4000、A4500を追加し、L4をRunPod対象として明示化した。
- RunPod GPU IDを公式名へ固定し、Rust cost policy、dispatch選択肢、matrix、summary表示を一致させた。
- Vast offer inventory workflowを追加し、Student/Teacher条件でoffer ID、GPU、VRAM、信頼度、rentable、料金、locationをartifact化する。
- Vast benchmark workflowを追加した。offer IDを入力し、instance作成、SSH実行、metrics/receipt収集、実行後破棄を行う。
- `rtf-score/smoke/vast/<gpu>/batch-<n>/`へ結果を保存できるよう、service result collectionへ`score_root`を追加した。

### CPU専用経路

- `.github/workflows/rtf-cpu-benchmark-run.yml`を追加した。
- `hf-inference-endpoint`と`runpod-pod`を選択できる。
- HF Inference Endpointは、CPU構成済みEndpoint URLへfixture WAVを送信する。Endpointの作成・更新・課金設定はworkflowの責務外であり、URL入力または`HF_INFERENCE_ENDPOINT_URL` secretを使用する。
- RunPodは公式の`compute-type cpu`でCPU Podを作成し、digest固定imageをSSH経由で実行して終了後に削除する。
- CPU providerは`provider=cpu`、`dtype=float32`、GPU telemetry=nullとして保存する。
- CPU価格が入力された場合は既存metrics契約の`gpu_price_per_hour`へ互換的に保存し、`cost_per_audio_hour`を算出する。価格未指定の場合はcost-based rankingから除外される。

### Result / ranking contract

- `build-rtf-benchmark-record.py`はLinux CPU実行を`provider_execution_proof=true`として受け入れる。
- metrics生成側は`RTF_COMPUTE_PRICE_PER_HOUR`を優先し、既存の`RTF_GPU_PRICE_PER_HOUR`をfallbackとして維持する。
- `vast`をservice metrics schemaへ追加し、RustのVast最低限metricsテストを追加した。
- `rtf-scores/smoke/runpod-pod/rtx3090/batch-32/metrics.json`のRTF、RTFx、CER、処理時間、音声時間、GPU価格、audio-hourコスト、VRAM、utilization、memory bandwidth、queue latency等をbenchmark recordへ変換できる境界を維持する。
- rankingの比較identityはmodel、decoder、dataset、manifest、precisionを使用する。`fixture_revision`と`image_digest`は追跡・再現性のためrecordへ保持するが、同一manifestのprovider比較を不必要に分断しない。

## 出力配置

```text
rtf-scores/smoke/hf-inference-endpoint/<cpu-target>/batch-<n>/
rtf-scores/smoke/runpod-pod/<cpu-target>/batch-<n>/
rtf-scores/smoke/runpod-pod/<gpu>/batch-<n>/
rtf-score/smoke/vast/<gpu>/batch-<n>/
```

`guarded`はbatch 1、`full-matrix`はbatch 1→8→32を順次実行する。各batchは独立したprovider実行として扱い、失敗時はblocked receiptへ記録して不要な課金を避ける。

## Secret契約

- `HF_TOKEN`: HF model/fixture/result repository、およびHF Inference Endpoint
- `RUNPOD_TOKEN`: RunPod CPU/GPU Pod
- `RUNPOD_REGISTRY_AUTH_ID`: private GHCR imageをRunPodへpullさせる場合
- `VAST_API_KEY`: Vast offer検索・Vast instance lifecycle
- `HF_INFERENCE_ENDPOINT_URL`: CPU HF Endpoint URL（dispatch inputでも指定可）

値そのものはworkflow、image、metrics、receiptへ保存しない。Repository Secretの名前だけをworkflowが参照する。

## 主要ファイル

- `.github/workflows/rtf-cpu-benchmark-run.yml`
- `.github/workflows/rtf-vast-benchmark-run.yml`
- `.github/workflows/vast-offer-inventory.yml`
- `.github/workflows/rust-workspace-release.yml`
- `scripts/ci/run-hf-inference-endpoint-cpu.py`
- `scripts/ci/publish-rtf-metrics.py`
- `scripts/run-runpod-cpu-benchmark.sh`
- `scripts/run-vast-benchmark.sh`
- `docs/rtf-cpu-benchmark-action-20260824.md`
- `docs/rtf-vast-benchmark-action-20260824.md`
- `docs/vast-offer-inventory-action-20260824.md`
- `docs/rtf-ada-gpu-benchmark-20260824.md`
- `docs/rust-workspace-release-action-20260824.md`

既存のRTF workflow、Rust cost policy、schema、matrix、provider adapter、service-result collection、関連docsも契約整合のため更新した。

## 検証結果

実行済みの対象検証：

```text
python -m py_compile scripts/ci/run-hf-inference-endpoint-cpu.py scripts/ci/publish-rtf-metrics.py scripts/ci/build-rtf-benchmark-record.py docker/rtf-benchmark/benchmark-runner/benchmark_runner/cli.py
bash -n scripts/run-runpod-cpu-benchmark.sh
python -c "import yaml; yaml.safe_load(...)"  # CPU workflow YAML
cargo fmt --all -- --check
cargo test --locked -p asr-contracts --lib
git diff --check
```

Rust testsは18件全件成功した。CPU/Vastの実provider起動、実HF EndpointへのHTTP測定、実RunPod CPU Pod、実Vast instanceはこのPR作成前には実行していない。これらは課金と外部credentialを伴うため、merge後に明示的なdispatchで確認する。

## 既知の制約と受入条件

1. HF Inference Endpoint CPUは、音声を受け取り`text`、`generated_text`、または`transcription`を返す既存Endpointを前提とする。
2. CPU価格を入力しない場合、`cost_per_audio_hour`はnullになり、cost rankingのaccepted inputにはならない。
3. RunPod CPU flavor availabilityはprovider側の当日capacityに依存する。
4. completed metricsはmetrics SHA、run identity、service、provider、environment、CPU targetを照合してからpersistする。

## 外部仕様の正本

- [HF Inference Endpoint CPU pricing](https://huggingface.co/docs/inference-endpoints/en/support/pricing)
- [HF Inference Endpoint configuration](https://huggingface.co/docs/inference-endpoints/guides/configuration)
- [RunPod CPU Pod CLI](https://docs.runpod.io/runpodctl/reference/runpodctl-pod)
- [RunPod Pod API](https://docs.runpod.io/api-reference/pods/POST/pods)
- [Vast Search Offers](https://docs.vast.ai/cli/reference/search-instances)
