# RTF Benchmark: HF Job / RunPod metadata と metrics の結合契約

## 目的

RTF Benchmark の完了結果に、Hugging Face Jobs APIまたはRunPod billing APIから取得した実行メタデータを結合する。これにより、metrics の性能値だけでなく、Job/Pod identity、GPU、課金対象時間、Job costを同じ immutable result revision から追跡できる。

## GitHub Actions の処理順

```text
HF Job / RunPod Pod 完了
  -> result receipt を取得
  -> providerのJob metadata / billing historyを取得
  -> HFはhardware pricing、RunPodはbilling historyを参照
  -> metrics URI と receipt の SHA-256 を検証
  -> provider_job / gpu_price_per_hour / cost_per_audio_hour を追加
  -> 同じ result path を新しい HF Dataset revision として保存
  -> receipt の URI / revision / SHA-256 を更新
  -> service result collection / asr-ranking
```

`scripts/run-benchmark.sh` がcompleted receiptを検知したとき、HFは`enrich_hf_job_metrics.py`、RunPodは`enrich_runpod_job_metrics.py`を実行する。metadataを取得できない場合はそれぞれ`HF_JOB_METADATA_UNAVAILABLE`または`RUNPOD_BILLING_METADATA_UNAVAILABLE`としてblockedにし、未検証のコストをrankingに流さない。

## metrics の追加フィールド

`evaluation/schemas/rtf-service-metrics.schema.json` の `provider_job` が正本である。

- HF Jobs: `job_id`, `url`, `namespace`, `flavor`, `billing_duration_sec`, `billed_minutes`, `unit_cost_usd_per_minute`, `job_cost_usd`
- RunPod: `job_id`, `url`, `gpu_type_id`, `billing_duration_sec`, `billed_seconds`, `job_cost_usd`
- HFの`cost_basis=hf_jobs_billed_starting_running_minutes`
- RunPodの`cost_basis=runpod_billing_history`

provider実行metricsには次の補助値も追加する。

- `memory_bandwidth_utilization_pct`: `nvidia-smi`の`utilization.memory`の実行中平均。GPUメモリコントローラ利用率であり、実効GB/sではない。
- `queue_latency_sec`: provider受付から実行可能状態までの時間。HFはJobの`scheduling_secs`、RunPodはPod作成開始からSSH readyまでを使用する。

preprocessing、decode、first-responseは現行NeMoの一括`transcribe()`境界内にあり、現在の実装では個別計測しない。推測値をRTF metricsへ混在させない。

HF Jobs は分単位の課金であるため、`billed_minutes = ceil(total_secs / 60)` とする。RunPodは公式billing historyの`amount`と`timeBilledMs`を使用する。`cost_per_audio_hour` は `job_cost_usd / (audio_duration_sec / 3600)` で、モデル推論単体のコストではなくJob全体の実行コストを音声時間へ換算した値である。RunPodのPod単価だけでなく、確定したbilling historyの実額を優先する。

## 不変性と受入れ条件

1. 元metricsのSHA-256がreceiptと一致しなければ停止する。
2. metadata 結合後の JSON を同じ path の新しい immutable revision に保存する。
3. 更新後 receipt の `metrics_uri`, `result_uri`, `metrics_sha256`, `result_sha256`, `result_revision` は新 revision を指す。
4. `provider_job` の flavor と Job ID は API 応答由来であり、環境変数や固定値で補完しない。
5. HF pricing APIが未知の単位を返した場合はfail-closedとする。
6. RunPod billing historyに対象Podの明細がない場合はfail-closedとする。
7. completed以外のreceiptはmetadata結合対象にしない。

## 既存結果への適用

既に保存された古い result は自動で書き換えない。新しい GitHub Actions 実行でこの結合処理を通し、更新された receipt を collection に渡す。過去結果を再処理する場合は、対象 Job と result revision を明示した別の再処理手順として扱う。

## 参照

- [Hugging Face Jobs pricing and billing](https://huggingface.co/docs/hub/en/jobs-pricing)
- [RunPod Pod pricing](https://docs.runpod.io/pods/pricing)
- [RunPod Pod billing history API](https://docs.runpod.io/api-reference/billing/GET/billing/pods)
- [HF Job metadata collector](../scripts/ci/enrich_hf_job_metrics.py)
- [RTF metrics schema](../evaluation/schemas/rtf-service-metrics.schema.json)
