# GPUサービス別RTF取得フロー

## 全体フロー

```text
固定revision/audio/manifest
        │
        ▼
RTF Verification Select
  service × GPU × model × dataset × decoder × batch
        │
        ├─ HF Endpoint / HF Jobs ── HF_TOKENで認証
        └─ RunPod Pod / Serverless ─ RUNPOD_TOKENで認証
        │
        ▼
provider側で実推論
  共通benchmark image + 固定manifest
        │
        ▼
metrics.jsonをHTTPS URIへ公開
  result_uri / result_sha256 / metrics_uri / metrics_sha256
        │
        ▼
RTF Service Result Collection
  download → SHA-256 → schema → artifact → rtf-scores/
```

## 事前準備

1. `evaluation/manifests/rtf-phase1.jsonl`のdataset revisionを固定する。
2. 音声をfloat32・mono・16 kHz・finite・C-contiguousへmaterializeし、音声とmanifestの
   SHA-256を確定する。
3. provider側で使用するbenchmark imageをdigest固定する。
4. provider側のGPU、decoder、batch、dtypeを選ぶ。
5. providerの結果を取得できるHTTPS `metrics_uri`を用意する。

GitHub repository secretsには次を登録する。

```text
HF_TOKEN       # HF Inference Endpoint / HF Jobs
RUNPOD_TOKEN   # RunPod Pod / RunPod Serverless
```

Actionsはserviceに応じて対応するsecretだけを使用し、tokenの値をログへ出力しない。
認証確認に失敗した場合、provider実行前にworkflowを停止する。

## 対象を一件選択して起動

`RTF Verification Select`を`Run workflow`から起動し、次を指定する。

- `service_id`: `hf-inference-endpoint` / `hf-jobs` / `runpod-pod` / `runpod-serverless`
- `gpu`: T4 / L4 / A5000 / RTX 3090 / RTX 4090
- `model_id`: ParakeetまたはKotoba Whisper
- `dataset_id`: Common Voice / JSUT / ReazonSpeech
- `decoder`: TDT / CTC / Whisper
- `batch_size`: 1 / 8 / 32
- `run_id`: 入力不要。選択内容とGitHub Actionsのrun IDから自動生成

workflowはPhase 1 matrixとの互換性、さらにserviceに対応するsecretの認証を確認する。
選択artifactは`rtf-verification-selection-<run_id>`である。

## provider別の実推論

### HF Inference Endpoint

1. HF Endpointを対象GPU・モデルdigest・固定revisionで起動する。
2. 固定manifestの音声を同一のHTTP推論経路へ送る。
3. warm-up回数、decode/resample、推論、postprocess、CER、VRAM、GPU utilizationを記録する。
4. `rtf_scope=service`のmetricsを保存し、`metrics_uri`を発行する。

### HF Jobs

1. `HF_TOKEN`で固定digestのbenchmark imageとGPU flavorを指定してJobを起動する。
2. Job内で固定manifestを読み、model RTFとservice RTFを分けて測る。
3. Job ID、結果URI、metrics SHA-256を保存する。

### RunPod Pod

1. `RUNPOD_TOKEN`でGPU typeを明示したPodを起動する。
2. 共通benchmark imageを使い、固定manifestを処理する。
3. PodのGPU telemetryとmetricsを保存し、停止後も取得可能なHTTPS URIへ置く。

### RunPod Serverless

1. `RUNPOD_TOKEN`でendpointを選択する。
2. cold-startとwarm invocationを分離して記録する。
3. request latency、queue、推論時間、CER、料金をmetricsへ保存する。
4. Pod結果とServerless結果を同じ`rtf_scope=service`形式で比較する。

## 結果を回収する

`RTF Service Result Collection`を起動し、selectionと同じ`run_id`・`service_id`を指定する。
`completed`の場合は次を必須にする。

- `job_id`
- `result_uri` / `result_sha256`
- `metrics_uri` / `metrics_sha256`

Actionsはmetricsを取得し、Rust validatorでSHA-256とschemaを検証する。成功すると次へ保存する。

```text
rtf-scores/<run_id>/<service_id>/service-result.json
rtf-scores/<run_id>/<service_id>/metrics.json
rtf-scores/<run_id>/<service_id>/summary.md
```

Actions botが保存commitを作成し、artifactにも同じ結果を保存する。

## 失敗・未検証の扱い

認証、GPU割当、固定revision、metrics URIのいずれかが不足した場合は、成功結果を作らず
`blocked`または`not_verified`で保存する。CPU実行やprovider registrationだけではCUDA、
DirectML、CoreMLの実推論証拠の代替にしない。
