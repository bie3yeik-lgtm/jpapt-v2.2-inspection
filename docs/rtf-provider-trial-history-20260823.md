# RTF Benchmark provider試行錯誤と現行到達点

更新日: 2026-08-23
対象: `jpapt-v2.2-inspection` のGitHub Actions、GHCR、RTF Resolver、Hugging Face Jobs、RunPod

## 1. 結論

RTF Benchmarkの最小実行経路は、RunPod RTX 3090のguarded batch 1で成立した。

検証済みの実行は次の通り。

- [GitHub Actions run 32629746571](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32629746571)
- provider: RunPod / GPU: RTX 3090
- image: `ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@sha256:67fae6c12ef6abb406b200984f81186da5a622a75b13ec476175193616d0b70c`
- model revision: `44edb27eea9317daf89333e75eb830db4b1cc298`
- dataset revision: `bf8819e8d9a5feb51b0c718686bd20ea67a3c729`
- fixture revision: `eb938860880292913212125844b851cef02211ac`
- manifest SHA-256: `9c47976f6101ebca1fc2575d46fde80d9a33dbc14b1e1f6dc2ca9aeb57a87694`
- `content_available: true`
- receipt / metrics: `completed`
- Pod cleanup: verified

取得できたmetricsは次の通り。

```text
audio_duration_sec:       5402.784
processing_duration_sec:  15.671496693976223
rtf:                       0.002900633579646387
rtfx:                     344.75226620037574
peak_vram_bytes:          5606215680
repeat:                   3
rtf_scope:                model
```

これは「RunPodのcontentとmetricsを取得できる」ことの証拠であり、HF/RunPod全GPU、
batch 8/32、ランキング、CER品質、full matrixの完了を意味しない。今回のreference
textは空白であり、CERは未計測である。

## 2. 正本フロー

```text
GHCR build/publish
  -> immutable image digest
  -> RTF Resolver
  -> fixture JSONL + fixture pointer + receipt
  -> RTF Benchmark Run
      -> immutable identity validation
      -> image loader safety validation
      -> provider credential/cost policy validation
      -> guarded batch 1
      -> provider Pod/Job
      -> content probe
      -> metrics
      -> result receipt and SHA-256 identity
      -> collect job validation
      -> score persistence / ranking input
```

### 2.1 Identityの不変条件

Benchmark実行は、次のidentityが一致するときだけ実行可能とする。

- image digestはGHCRの`sha256:`固定値である。
- fixture pointerとfixture receiptのrepository/revisionが一致する。
- fixture receiptのimage digestが実行image digestと一致する。
- model、dataset、fixture、manifestのrevisionはfloating値でない。
- provider receiptの`run_id`、status、metrics SHA-256、result URIがcollect jobの
  入力と一致する。

Resolverが生成したfixtureをmainへ届ける処理には、過去に生成差分をresetで失う問題が
あった。PR #438で生成差分保存・再適用を修正し、Resolver run
`32629283884` からPR #439を生成・mergeした。以後、benchmarkはmainに存在する
fixture pointerを正本として使用する。

## 3. 失敗の時系列と原因境界

### 3.1 GHCR / Resolverのidentityずれ

GHCR build後にResolverが生成したreceiptを、Resolver自身の作業ツリーresetで失う
経路があり、古いimage digestのreceiptが残った。これはprovider実行ではなく、生成物の
delivery問題だった。

対応:

- Resolver生成差分を一時patchへ保存。
- `origin/main`へのreset後にpatchを再適用。
- fixture pointer、receipt、image digestの一致をbenchmark前に検証。

証拠: PR #438、Resolver PR #439、main commit `bd7349b`。

### 3.2 HF JobsのCUDA illegal access

HF Jobsの実行では、結果・metricsを出せないままCUDA illegal accessとなった。
receiptは次の型付き失敗になった。

```text
PROVIDER_CUDA_ILLEGAL_ACCESS
status: blocked
metrics_sha256: null
result_sha256: null
```

これはresult collectionやrankingの問題ではなく、provider内の推論実行失敗である。
失敗時にmetricsを作ったことにせず、blocked receiptとしてcollectへ渡す。

対応:

- CUDA OOM、illegal access、driver incompatibilityを別error codeで分類。
- OOMを検知した後のguarded batch拡大を停止。
- `num_workers=0`、`pin_memory=false`、`use_lhotse=false`のloader policyを固定。
- CUDA diagnosticsは明示opt-inとし、通常のguarded smokeで不要な追加コストを避ける。

### 3.3 HF content probeの失敗

別のHF runではモデルrestoreは成功したが、次のcontent probeで停止した。

```text
PROVIDER_CONTENT_PROBE_FAILED
error_message: NeMo transcription DataLoader policy was not applied
content_available: false
```

モデルをロードできたことは、fixture音声がproviderで利用可能であることを意味しない。
content probeをmetricsより前の必須gateとし、loader policy適用とローカル音声存在を確認
できない場合は推論・rankingを実行しない。

### 3.4 RunPod driver互換性

旧RunPod実行では、containerのCUDA runtimeとhost NVIDIA driverの不一致が確認された。

```text
The NVIDIA driver on your system is too old
```

対応:

- RunPod adapterに最低CUDAバージョンgateを追加。
- 現行Actions laneでは`RTF_RUNPOD_MIN_CUDA_VERSION=13.2`を使用。
- providerが実行開始する前に不適合を`PROVIDER_CUDA_DRIVER_INCOMPATIBLE`として停止。

これにより、driver不適合でGPU時間を消費してからCUDAエラーになる経路を閉じた。

### 3.5 RunPodの環境変数転送

RunPod Podは作成できたが、SSH経由entrypointで`RTF_DATASET_ID is required`となった。
Pod作成時の`--env`が実際のSSH実行環境で保証されなかったことが原因だった。

対応:

- benchmark値をPod control-planeの`--env`へ依存しない。
- allowlist済み環境ファイルをSSH経由で`/run/rtf-benchmark.env`へ転送。
- mode `0600`を設定し、明示的なentrypoint実行時だけsource。
- `HF_TOKEN`はPod metadataへ入れない。

### 3.6 RunPodのshell quoting

複合`bash -lc` commandのquote再構成により、転送した環境ファイルが確実にsourceされ
なかった。

対応:

- `tee`で環境ファイルを転送。
- `chmod 600`を単純なremote commandで実行。
- `bash -s`へ短いscriptをstdinで渡す。
- Pod IDなど必要な値だけをscript内で安全にquoteする。

### 3.7 RunPodのPython executable / package path

HF JobsとRunPod SSH shellではPATHが異なり、`python`が見つからない失敗が発生した。
その後、interpreterは解決できても`benchmark_runner` package discoveryが失敗する
経路が残った。

対応:

- `python`、`python3`、既知のvirtualenv/Conda/system pathの順でinterpreterを解決。
- `/opt/rtf-benchmark/benchmark-runner`を`PYTHONPATH`の先頭へ明示。
- `benchmark_runner/__init__.py`の存在を推論前に確認。
- package欠落imageはfail-closed。

### 3.8 SSH key / runtime initialization / endpoint readiness

RunPodでは次の段階が独立して失敗した。

1. Podが`initializing`のままruntimeへ到達しない。
2. runtimeは`running`だがSSH endpointがすぐ公開されない。
3. SSH keyのauthorized_keys materialization不備でpublickey認証に失敗する。

対応:

- runtime availability、SSH info、SSH handshakeを別々に観測。
- bounded readiness timeoutとSSH info grace periodを設ける。
- image側で`PUBLIC_KEY`から`authorized_keys`をmaterializeし、権限と`sshd_config`を検証。
- container log streamをPod実行中にActionsへ表示し、entrypoint・content probe・推論の
  境界を追跡可能にする。

### 3.9 RunPod account balanceとinstance availability

RunPodでは次の2種類を別々に扱う必要があった。

- 残高不足: Pod作成前に`RUNPOD_ACCOUNT_BALANCE_TOO_LOW`。
- GPU供給不足: RTX 4090のguarded smokeで`RUNPOD_NO_INSTANCE_AVAILABLE`。

後者の実行 [32629486660](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32629486660)
はPod IDなし、phase=`pod_create`で停止した。image pull、SSH、NeMo、CUDA、metricsには
到達していない。したがって、同じ失敗をprovider推論失敗として修正しない。

## 4. 最終成功runの証拠

RTX 3090 runでは次の境界をすべて通過した。

```text
GHCR immutable image validation       PASS
fixture/revision identity validation PASS
RunPod Pod creation                   PASS
runtime/SSH readiness                 PASS
private GHCR image pull               PASS
fixture download                      PASS
content probe                         PASS
NeMo model restore                    PASS
CUDA inference                       PASS
metrics generation                   PASS
HF Dataset result upload              PASS
receipt SHA/result identity           PASS
collect job contract validation       PASS
Pod cleanup                           PASS
```

実行結果の意味は次の通り。

- `content_available=true`により、期待音声がprovider container内で利用可能だった。
- `status=completed`かつmetrics/result SHA-256が存在し、collection contractが成立した。
- RTFとRTFxは取得できたが、reference textが空白のためCERは評価していない。
- `peak_vram_bytes`は以後のGPU別batch sizingの初期観測値であり、batch 8/32の安全性を
  推定する根拠にはしない。

## 5. 現行の実行ルール

### guarded

- batch 1のみ。
- 失敗時は残りのprovider実行を開始しない。
- Pod/Job作成、image pull、model download、dataset downloadの時間を含むbounded timeoutを
  適用する。
- completed receipt、content evidence、metrics/result identityがそろわなければ成功扱いに
  しない。

### full-matrix

- 明示的な`cost_mode=full-matrix`が必要。
- batch 1/8/32を実行するが、batch 1成功はbatch 8/32のメモリ安全性を保証しない。
- GPUごとに`peak_vram_bytes`、provider runtime、OOM有無を記録する。
- OOMやillegal accessが出た時点で以後の高コスト試行を停止し、失敗receiptを保存する。

### ranking

ランキングへの投入条件は、単にRTF値があることではない。

1. content probe completed。
2. provider receipt completed。
3. metrics/result URIとSHA-256が一致。
4. image/model/dataset/fixture/manifest identityが一致。
5. provider、GPU、profile、batch、repeatが記録済み。
6. CERが必要なランキングでは、reference textが非空で品質指標が計算済み。

## 6. 未完了項目

- HF JobsとRunPodの全組み合わせの比較。
- `1/8/32` full matrixの完走。
- 有効なreference textを用いたCER/WERとranking。
- `asr-rtf-rank`へのcompleted metricsの自動投入と成果PR。
- provider別の価格・GPU utilizationの完全な収集。
- RunPod container log APIの最新版CLIでの外部検証。ただし今回のreceipt/metrics取得は
  SSH stdout経路で成立している。

## 7. 変更・証拠の参照

- CUDA compatibility gate: PR #437
- RunPod receipt stream recovery: `TelopFlow_Feature/docs/work_history/2026-08-23-rtf-actions-runpod-receipt-stream.md`
- Resolver generated delivery fix: `TelopFlow_Feature/docs/work_history/2026-08-23-rtf-resolver-generated-delivery-fix.md`
- OOM/cost gate: `TelopFlow_Feature/docs/work_history/2026-08-23-rtf-actions-oom-gate.md`
- RunPod readiness: `TelopFlow_Feature/docs/work_history/2026-08-23-rtf-runpod-guarded-readiness.md`
- RunPod package/runtime: `TelopFlow_Feature/docs/work_history/2026-08-23-rtf-runpod-package-path.md`
- 最小成功run: `TelopFlow_Feature/docs/work_history/2026-08-23-rtf-runpod-smoke-completed.md`

## 8. 受入判定

| 項目 | 判定 |
| --- | --- |
| GHCR digest発行 | verified |
| RTF Resolver fixture生成・main反映 | verified |
| HF providerのcontent/metrics経路 | batch 1の一部runでverified、全組合せは未完了 |
| RunPod Pod/SSH/container実行 | RTX 3090 batch 1でverified |
| RunPod content probe | verified |
| RunPod metrics/result receipt | verified |
| OOM/illegal access防止 | gateとtyped receiptはverified、全GPU安全性は未検証 |
| full matrix 1/8/32 | not verified |
| ranking | blocked pending valid quality/reference inputs |
