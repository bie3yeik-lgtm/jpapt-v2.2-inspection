# RTF Benchmark 現行実行フロー

更新日: 2026-08-21
対象: HF Jobs / RunPod Podで実行するRTF Benchmark smoke
正本: `.github/workflows/rtf-resolver.yml`、`.github/workflows/rtf-benchmark-run.yml`、`.github/workflows/benchmark-ranking.yml`

## 1. 目的と受入範囲

0〜100 users規模の初期サービス選定を目的に、`docs/Calculare-RTF-Score.md`の最終表にある
全有効組み合わせを、固定fixtureと共通GHCR imageで比較する。各組み合わせでは
`batch=1/8/32`を測定し、completed recordだけから上位3位のランキングを自動生成する。

このBenchmarkは、ユーザー負荷、autoscaling、API可用性、bootstrap URLの本番配布、モデル改善
効果を証明するものではない。ランキング確定後に、それらを別runとして実働試験へ進める。

## 2. 現行profile

| profile | 用途 | 実行場所 |
|---|---|---|
| `smoke` | 現行Benchmark。0〜100 usersの初期サービス選定 | HF Jobs / RunPod Pod |
| `pref` | 比較候補の優先実行 | Resolver / Result / Rankingの契約対象 |
| `probe` | 20〜50時間、100〜300本、短尺〜1時間超混在の大規模確認 | 専用fixture・実行として分離 |

現行の外部Benchmark Runは`smoke`に限定する。旧profile名は使用しない。ローカルGPU smokeは
受入条件に含めない。

## 3. 実行シーケンス

```text
source-controlled Dockerfile
  -> GHCR Build / Publish
  -> immutable image digest
  -> RTF Resolver (GitHub Actions)
  -> fixed manifest + materialized audio + HF fixture revision
  -> RTF Benchmark Run (GitHub Actions)
       -> HF Jobs or RunPod Pod
       -> image pull / model and dataset preparation
       -> batch 1, 8, 32 remote inference
       -> result/metrics URI + SHA-256 + provider receipt
  -> RTF Service Result Collection
       -> schema / identity / SHA validation
       -> benchmark-record.json
  -> benchmark-ranking.yml
       -> Rust ranking validation
       -> ranking.json / ranking.md (top 3)
       -> ranking PR
  -> selected service evidence
       -> bootstrap URL API / model improvement trials
```

## 4. Step 1: GHCR imageを固定する

GHCR buildはDockerfileのimport/version smokeとmetadataを検証し、publish後に次のdigestを発行する。

```text
ghcr.io/<owner>/parakeet-rtf-benchmark@sha256:<64-hex>
```

Benchmark、Resolver、provider executionはtagや`latest`をidentityに使わない。image digest、
source commit、runner version、CUDA/ORT/NeMo環境を同じrun identityへ結び付ける。token、音声、
model fileはimage layerへ入れない。

## 5. Step 2: RTF Resolverでfixtureを作る

ResolverはGitHub Actions上でdigest固定imageを起動し、dataset revisionを固定してmaterialized
audioとJSONL manifestを作る。現行smokeの主な条件は次のとおりである。

```text
dataset: japanese-asr/ja_asr.common_voice_8_0
profile: smoke
sample count: 20-50
total audio: approximately 1.5 hours
sample duration: approximately 30 seconds-10 minutes
audio: float32 / mono / 16000 Hz / finite / C-contiguous
```

Resolverは次を保存・publishする。

```text
rtf-scores/benchmark/benchmark-v1.jsonl
rtf-scores/benchmark/benchmark-v1.jsonl.sha256
rtf-scores/benchmark/benchmark-v1.receipt.json
rtf-scores/benchmark/benchmark-v1.fixture.json
```

Benchmark Runはfixture repository ID、fixture revision、manifest SHAをこのpointer/receiptから
読み取る。手入力のfixture revisionやmanifest差し替えは許可しない。

## 6. Step 3: HF Jobs / RunPodでsmokeを実行する

GitHub Actionsの`RTF Benchmark Run`は、providerとGPUを選び、同一image・同一fixtureでリモート
実行する。対象matrixは次の6 service/GPUである。

| service | GPU |
|---|---|
| HF Jobs | T4、L4 |
| RunPod Pod | A5000、L4、RTX 3090、RTX 4090 |

model、互換decoder、dataset、precisionの全有効組み合わせを対象にし、各provider/GPUで
`batch=1/8/32`を順次実行する。repeatはrunner内で固定管理し、matrix軸へ重複させない。

### Provider固有の境界

- HF Jobs: `HF_TOKEN`、HF flavor、固定image digest、Job ID、metrics URIを使用する。
- RunPod Pod: `RUNPOD_TOKEN`、GPU type、Pod ID、image pull/SSH ready、entrypoint、cleanupを使用する。
- tokenはログ、Docker layer、metrics、Git artifactへ出力しない。
- provider登録、Job/Pod作成、GPU execution proof、metrics生成を別々に検証する。
- CPU fallback、provider registrationだけではCUDA smoke成功としない。

### 失敗時の扱い

image pull、model/dataset download、provider起動、OOM、timeout、metrics生成の各段階をreceiptへ
記録する。OOMやtimeoutでmetricsがないbatchは`blocked`または`not_verified`として保存し、
completed recordへ補完しない。少なくとも1つのbatchだけ成功した場合も、欠落batchを成功扱いにしない。

## 7. Step 4: result/metricsを回収する

provider receiptには次を含める。

```text
run_id
job_id
status
result_uri / result_sha256
metrics_uri / metrics_sha256
error_code / error_message
```

`RTF Service Result Collection`はURIからpayloadを取得し、result/metricsのSHA-256、schema、
run identity、profile、provider/GPU、batch、manifest SHA、image digestを検証する。検証済みの
metricsだけを`benchmark-record.json`へ変換する。

## 8. Step 5: rankingを自動生成する

`benchmark-ranking.yml`はprofile単位でrecordを収集し、Rust `asr-rtf-rank`へ渡す。
異なるprofile、manifest、image digest、provider identityを同じランキングへ混在させない。

採用条件:

- schema valid
- `status=completed`
- provider execution proofが存在
- RTF、CER、costが有効
- result/metrics SHA-256が一致
- model/dataset/fixture/image identityが一致
- duplicate run、期待cell欠落、profile mismatchがない

sort keyはRust contractで固定し、`ranking.json`と`ranking.md`へ上位3位を出力する。表には
service、GPU、model、decoder、dataset、batch、RTF、RTFx、CER、`$/audio-hour`を残す。

## 9. Step 6: ranking PRと後続実働試験

Ranking Actionsは差分がある場合だけ専用inspection branchへcommitし、main向けPRを作成する。
PRには測定条件、digest、manifest SHA、provider receipt、blocked batchを含める。

上位3位のうち採用候補を選定した後、次を別のrun identityと受入条件で行う。

```text
accepted top-3 ranking
  -> selected service / GPU
  -> bootstrap URLによるAPI配布試験
  -> 0-100 users相当のAPI実働試験
  -> モデル改善の実働試験
```

ランキングは最適サービスの候補根拠であり、API配布やモデル改善の成功証明ではない。

## 10. 検証と未検証境界

本変更で行う検証:

- active RTF profileの旧表記残存チェック
- JSON schema/manifest parse
- Python compile
- shell syntax
- Rust contractの対象crate test
- `git diff --check`

外部で別途必要な受入:

- GHCR remote digestの実発行
- ResolverのHF Dataset publish
- HF Jobs / RunPodの実GPU smoke
- result/metrics URIの再取得
- top-3 ranking PRのActions実行
- bootstrap URL APIとモデル改善の実働結果

これらをlocal static checkやDocker buildだけで成功扱いにしない。
