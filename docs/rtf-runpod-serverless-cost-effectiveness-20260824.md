# Parakeet RTF Serverless費用対効果調査

## 1. 目的

`nvidia/parakeet-tdt_ctc-0.6b-ja`をRunPod Serverlessで小規模な推論/API用途へ配置する
場合のGPU候補を、料金、VRAM、cold start、OOM余裕、実測ランキングの再現性で比較する。

対象はServerless endpointのworkerであり、常時起動するRunPod Podの比較ではない。

## 2. RunPod Serverlessの前提

RunPod Serverlessは実際に使用したcompute timeに対する従量課金で、リクエストがない間の
idle compute costは発生しない。workerが存在しない状態では、コンテナ起動、モデルのGPU
ロード、runtime初期化を含むcold startが発生する。workerはリクエスト後しばらく維持され、
idle後に停止する。

参照: [RunPod Serverless Overview](https://docs.runpod.io/serverless/overview)

Serverlessの現行価格はGPUの料金グループとして表示されるため、同じ料金でも実GPUが混在する
場合がある。厳密なRTF比較では、割り当てられた実GPU名をmetricsとreceiptへ保存し、GPUが
一致しないrecordを同一ランキングへ混在させない。

参照: [RunPod GPU Cloud Pricing](https://www.runpod.io/pricing)、
[RunPod GPU types](https://docs.runpod.io/flash/configuration/gpu-types)

## 3. 候補一覧

RunPod公式価格ページのServerless表示を基準にする。価格は変動するため、下表は調査時点の
USD/実時間であり、実請求の正本ではない。

| 優先度 | Serverless GPUグループ | VRAM | 料金 | Parakeet用途 |
|---:|---|---:|---:|---|
| 1 | A5000 / L4 / RTX 3090 / MIG 24GB | 24GB | $0.69/h | 標準候補 |
| 2 | RTX 4090 | 24GB | $1.10/h | レイテンシ・速度重視 |
| 3 | A40 / RTX A6000 | 48GB | $1.22/h | OOM・長尺・大batch対策 |
| 4 | A4000 / A4500 / RTX 4000 / RTX 2000 | 16GB | $0.58/h | guarded実験専用 |
| 5 | RTX 5090 | 32GB | $1.58/h | 将来の高速化・余裕枠 |

## 4. 推奨判定

### 第一候補: A5000 / L4 / RTX 3090

Parakeet 0.6Bの小規模Serverless endpointでは、まず24GBクラスを採用する。

- A5000: 現行Pod基準と比較しやすい。
- L4: 推論・低消費電力・低発熱を重視する場合に適する。
- RTX 3090: 高スループット比較に適する。
- MIG 24GB: 実GPU性能の再現性が低いため、厳密なRTFランキングでは個別測定対象にしない。

RunPodのServerless料金ではこれらが同じ24GB料金グループに含まれるが、同一GPUであることは
保証されない。GPU別の比較が必要な場合は、特定GPU指定または実GPU名の検証を必須とする。

### 第二候補: RTX 4090

24GBを維持しつつ処理時間短縮を狙う候補。ただし$1.10/hで24GB標準グループの約1.6倍のため、
処理時間が十分に短縮されることを実測で確認できない限り、費用対効果はA5000/L4/RTX 3090に
劣る。

### OOM対策: A40 / RTX A6000

48GB VRAMを必要とする場合の安全枠である。

- 長尺音声
- batch 32以上
- 複数モデル常駐
- NeMo/PyTorchの一時メモリ増加

通常のParakeet 0.6B・小batchでは過剰であり、通常経路ではなくOOM時のfallbackまたは別の
benchmark cellとして扱う。

### 16GBクラス

最安だが、現在のCUDA OOM・NeMo runtimeの実績を踏まえ、本番候補にはしない。使用する場合は
batch 1、短尺fixture、早期停止を備えたguarded smokeに限定し、成功率とpeak VRAMを確認する。

## 5. ServerlessとPodの境界

```text
断続的なAPI利用、低利用率
  -> Serverless A5000/L4/RTX 3090

常時warm、頻繁なリクエスト
  -> Pod A5000

OOM耐性、長尺、大batch
  -> Serverless A40/RTX A6000
```

Serverlessでactive workerを常時1台維持する場合は、24GBクラスでも約$0.69/hとなる。RunPod
PodのA5000表示価格$0.27/hより高いため、常時warm運転はPodの方が経済的である。Serverlessは
「常時GPUを確保する」ためではなく、workerを必要時だけ起動する用途に適する。

## 6. RTF Benchmarkへの適用

Serverlessの候補をランキングへ追加する場合は、最低限次をmetricsへ保存する。

- 実GPU名とGPU type ID
- Serverless料金グループと実請求単価
- queue latency
- cold start / model load時間
- inference processing時間
- billed duration、job cost
- image digest、model revision、dataset/fixture revision

GPU料金グループだけでは実測GPUを識別できないため、A5000/L4/RTX 3090を同じrecord集合へ
無条件に混在させない。`service_id=runpod-serverless`と実GPU名をidentityへ含め、同一GPU・
同一image・同一fixture・同一batchの完成metricsだけをランキングへ渡す。

## 7. 結論

小規模なServerless運用の第一候補は、次の順序とする。

```text
1. A5000 / L4 / RTX 3090 24GB group
2. RTX 4090（速度が必要な場合）
3. A40 / RTX A6000（OOM・長尺・大batch）
4. 16GB group（guarded smokeのみ）
```

実運用の採用判断は、価格表ではなく、同一fixtureに対する以下の値で行う。

```text
cost_per_audio_hour
 + cold_start_seconds
 + queue_latency_seconds
 + successful_completion_rate
 + RTF
```

特にServerlessでは、単純なGPU時間単価ではなく、cold startと失敗再試行を含む実コストで
比較する。
