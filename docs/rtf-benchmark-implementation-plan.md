# RTFベンチマーク再構築 実装計画

## 目的

このRepositoryに残す成果は、Workflowの選択履歴やArtifact回収履歴ではなく、固定条件で
実推論したRTFベンチマーク結果である。最終成果は、GPU/serviceごとの `RTF`、`RTFx`、
`CER`、処理対象音声時間、処理時間、VRAM、GPU utilization、料金、入力条件、再現用の
revisionとSHA-256を持つ機械可読なベンチマークとする。

参照した方針は、共通Docker image、固定dataset、GitHub Artifactを唯一の保存先にしない
設計、Phase 1の6組、ランキング自動生成、`benchmark-phase1.yml`、`benchmark-full.yml`
である。現在の`rtf-verification-select.yml`は対象選択だけを行うため、ベンチマーク本体へ
置き換える。

## 成果物と保存境界

`rtf-scores/`直下には履歴ファイルを置かない。既存の選択履歴・回収履歴は
`rtf-scores/run_summary_history/`へ移し、将来のベンチマーク成果は次の構造にする。

```text
rtf-scores/
├── run_summary_history/       # 既存の選択・回収履歴。ランキング入力ではない
├── phase1/
│   ├── matrix.json
│   ├── results.jsonl
│   └── summary.json
├── full/
│   ├── matrix.json
│   ├── results.jsonl
│   └── summary.json
└── ranking.json
```

大きな音声、モデル、テンソル、Docker layer、providerの生ログはGitへ保存しない。GitHub
Artifactは短期の受け渡しに使い、同じpayloadを外部のimmutable object storageへ保存し、
URIとSHA-256をベンチマーク結果へ記録する。

## 共通benchmark image計画

1. `docker/rtf-benchmark/`を新設し、benchmark専用imageのDockerfileと固定依存lockを追加する。
2. imageにはRust/Pythonの薄いrunnerだけを入れ、モデルexportやdataset取得を実行時に
   変更しない。
3. imageをdigest固定して`benchmark-build.yml`でbuild・pushし、matrix workflowはその
   digest以外を使用しない。
4. image metadataにrunner version、ORT/CUDA version、OS、commit SHAを保存する。
5. providerごとのwrapperはHTTP/Pod/Job起動だけを担当し、RTF計算と結果schemaは共通runner
   に集約する。

受入条件は、同一image digest・同一runner version・同一入力manifestで全providerを実行
でき、CPU fallbackやprovider登録だけでは成功としないことである。

### Docker実装ディレクトリ

```text
docker/rtf-benchmark/
├── Dockerfile
├── requirements.lock
├── benchmark-runner/
├── entrypoint.sh
├── README.md
└── .dockerignore
```

`Dockerfile`はbase image、CUDA/ORT/PyTorch/NeMo/ffmpeg、runner revisionを固定する。
build後にGHCRの`ghcr.io/<owner>/parakeet-rtf-benchmark@sha256:<digest>`を確定し、
Phase 1とFullのrecordへ保存する。`latest`などのmutable tagはbenchmark inputに使わない。

## 固定dataset計画

1. Phase 1のcanonical datasetは`japanese-asr/ja_asr.common_voice_8_0`とし、dataset
   revisionをlockする。JSUTとReazonSpeechはFullまたは比較拡張時に追加する。
2. `evaluation/manifests/rtf-phase1.jsonl`をcanonical manifestとし、サンプルID、音声
   SHA-256、duration、dataset revisionを解決済みデータとして保存する。
3. 毎回のランダム抽出は禁止する。Phase 1は固定subset、Fullは固定した全評価対象を使う。
4. 音声はfloat32・mono・16kHz・finite・C-contiguousへmaterializeし、materialized file
   のSHA-256をmanifestに記録する。
5. benchmark開始時にmanifest SHA-256とdataset lock SHA-256を検証し、不一致なら実行を
   `BLOCKED`にする。

## Phase 1: `benchmark-phase1.yml`

### 対象

参照表の6組だけを対象とする。

| service | GPU |
|---|---|
| HF Inference Endpoint | T4, L4 |
| RunPod Pod | A5000, L4, RTX 3090, RTX 4090 |

各組でParakeet TDT、Parakeet CTC、Kotoba Whisperを対象にし、batch 1/8/32を測る。
datasetは固定Phase 1 subset、repeatはrunner内で3回とする。GitHub matrixはprovider/GPU
の6組を展開し、repeatをmatrix軸にしない。

### Workflow責務

- `benchmark-build.yml`のimmutable image digestを検証する。
- Repository secret `HF_TOKEN`をHF Inference Endpointの認証に使用する。
- Repository secret `RUNPOD_TOKEN`をRunPod Podの認証に使用する。
- fixed manifestとdataset lockを検証する。
- provider実行をdispatchし、job IDとresult URIを受け取る。
- providerの完了を待つ処理と結果回収を分離する。
- 完了後、common result schema、metrics schema、result/metrics SHA-256を検証する。
- `phase1/results.jsonl`へ一行のimmutable recordを追加する。

### 計測契約

`RTF_model`と`RTF_service`を分ける。集計RTFは個別RTFの平均ではなく、総処理時間÷総音声
時間とする。warm-up、model load、decode、resample、frontend、encoder、decoder、postprocess
を個別に記録し、batch 1 latencyとbatch 8/32 throughputを混同しない。

## ランキング自動生成Workflow

`benchmark-ranking.yml`を追加し、Phase 1またはFullの完了、または手動dispatchを起点にする。

1. `phase1/results.jsonl`と`full/results.jsonl`を取得する。
2. schema、manifest SHA、image digest、重複run、provider境界、SHA-256を検証する。
3. `status=completed`かつ必要なRTF/CER/料金が揃ったrecordだけをランキング対象にする。
4. `$/audio-hour = gpu_price_per_hour * RTF_service`を計算する。
5. provider、GPU、batch、decoder、RTF scope別に安定したsort keyでランキングする。
6. `rtf-scores/ranking.json`と人間向け`ranking.md`を生成する。
7. ベンチマーク成果だけを`inspection/rtf-benchmark-<run-id>`へcommitし、main向けPRを作る。

`BLOCKED`、`NOT_VERIFIED`、metrics不足、provider fallback、manifest不一致のrecordは
ランキングへ推測で含めない。履歴保存WorkflowはランキングWorkflowを代替しない。

## Full: `benchmark-full.yml`

Phase 1の結果から上位候補を機械的に選び、Full測定へ進める。

1. `phase1/summary.json`のcandidate selectionを検証する。
2. 原則として各providerの上位3 GPU、各モデル、必要なdecoder、batchを対象にする。
3. Phase 1で使ったimage digest、dataset revision、manifest契約を再利用する。
4. 固定subsetから全固定評価対象へ拡張し、repeat、warm/cold、model/service scopeを分離
   して記録する。
5. Phase 1との比較可能性を維持し、FullがPhase 1の入力や計算式を上書きしない。
6. 完了後に`benchmark-ranking.yml`を起動し、Phase 1とFullのランキングを更新する。

FullはPhase 1が成功していない場合に開始しない。上位候補の選定ができない場合は
`BLOCKED`として理由を保存する。

## 実装順序

1. 既存`rtf-scores/`を履歴領域へ整理する。
2. `japanese-asr/ja_asr.common_voice_8_0`のrevision lockとresolved manifestを確定する。
3. benchmark result schema、immutable artifact recordを確定する。
4. `docker/rtf-benchmark/`の共通Docker imageとrunnerを実装する。
5. `benchmark-build.yml`を実装し、GHCR digestを公開する。
6. `benchmark-phase1.yml`とHF/RunPod provider adaptersを実装する。
7. `HF_TOKEN`/`RUNPOD_TOKEN`を使う外部保存とArtifact retentionを実装する。
8. `benchmark-ranking.yml`を実装する。
9. Phase 1の実測結果を入力に`benchmark-full.yml`を実装する。
10. 実測runで成果ファイル、SHA、ランキング、PR内容を検証する。

## 検証と受入条件

- 固定manifestのrevision、音声SHA、image digestが同一runに記録される。
- CPU fallbackをCUDA実行成功として扱わない。
- provider execution proofとnode assignment proofを分離する。
- candidate outputがexpected/referenceを上書きしない。
- 少なくとも一つの実GPU実測があり、RTF/CER/料金の欠落を明示する。
- `rtf-scores/`のPR差分が履歴ではなくbenchmark payload、summary、rankingだけになる。
- 外部保存先からpayloadを再取得し、SHA-256が一致する。
- `HF_TOKEN`と`RUNPOD_TOKEN`の値がログ、Docker layer、metrics、Gitへ漏れない。
- Phase 1 recordのdatasetが`japanese-asr/ja_asr.common_voice_8_0`の固定revisionと一致する。
- Phase 1/Fullが同一のimmutable Docker image digestを使う。

## 現状との移行方針

`rtf-verification-select.yml`と`rtf-verification-artifact-persist.yml`は移行期間の選択・
履歴回収用として`run_summary_history/`へ閉じ込める。新しいbenchmark Workflowが成果を
生成できるまで削除せず、ランキング入力には使用しない。`rtf-service-result.yml`も
provider結果envelopeの互換入口として残すが、benchmark recordへの変換を通らない結果は
最終ランキングへ含めない。
