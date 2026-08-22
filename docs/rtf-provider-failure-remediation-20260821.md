# RTF provider failure remediation

確認日: 2026-08-21
対象: HF Jobs T4 smoke / GHCR publish後のRTF Resolver連続実行

## Confirmed failures

### HF Jobs

Job `6a87d1949cd058584adc4f4be` は、GHCR digest、model revision、fixture
revision、content probeまでは成功した。本測定のNeMo `transcribe()` 中に
`CUDA error: an illegal memory access was encountered` が発生し、metricsと
`RTF_RESULT_RECEIPT`を生成できなかった。

ログにはpinned allocator警告と、non-tarred datasetでのworker/tokenization警告も
存在した。これはCUDA illegal accessの直接原因と断定せず、再現時の診断対象とする。

### GHCR連続Resolver

Run `32445489921`では、GHCR build/publish、digest解決、image provenanceは成功した。
後続Resolverへ `inspection_profile: lough inspection` が渡され、Resolverの現行値
`smoke|pref|probe` に一致しないため `unknown inspection profile` で停止した。

## Implementation boundary

- benchmark batch `1/8/32`、fixture、model revision、digest identityは変更しない。
- NeMoのtyped `override_config` が利用できる場合は、そこへ
  `num_workers=0`、`pin_memory=false`、`use_lhotse=false` を設定する。
- NeMoが一時DataLoaderの `pin_memory=True` を内部固定する版にも対応するため、
  DataLoader生成境界で実効値を `num_workers=0`、`pin_memory=false`、
  `persistent_workers=false`、`prefetch_factor=None` に固定し、適用後の値を検証する。
- typed overrideを持たない旧APIでも `num_workers=0`、`use_lhotse=false` を渡し、
  同じDataLoader検証を行う。
- `RTF_CUDA_DIAGNOSTICS=1` のときだけ同期CUDA診断を有効にする。
- Jobがreceiptを出せず終了した場合も、provider failureをtyped receiptとして保存する。
- metricsがない失敗をcompletedとして公開しない。
- GHCR連続Resolverとrankingの古いprofile名を現行profileへ統一する。

Actions側の追加対策:

- `RTF Benchmark Run` はJob timeoutをGitHub Actions上限の360分へ拡張し、
  image/model/fixture取得を含む1/8/32直列実行を180分で打ち切らない。
- provider adapterへ `RTF_NUM_WORKERS` を渡さず、worker数・pinned memory・Lhotse利用は
  image内の固定policyだけを正本とする。
- provider実行前にdigest固定GHCR imageをpullし、`transcribe_compat.py` のloader safety
  policyをimage内部で検証する。ソース修正前の古いdigestを誤って実行しないためである。
- 既存のHF/RunPod receipt正規化、content gate、cost guard、Pod cleanupは維持する。

## Acceptance evidence

Static/unit evidence:

- `transcribe_compat`がtyped overrideと実DataLoaderの両方へ安全設定を適用する。
- unsupportedなNeMo引数を渡さない。
- hard-codedなNeMo temporary DataLoaderに対しても実効値を検証する。
- CUDA診断モードが同期設定を有効化する。
- illegal access/OOM/一般provider失敗を別error codeでreceipt化する。
- GHCR連続Resolverが`smoke`を渡す。

External evidence:

- 新digestを使ったHF T4 smokeでcontent probeと本測定を再確認する。
- completed時はmetrics URI/SHAとreceipt identityを確認する。
- 失敗時はJobが長時間待機せず、typed blocked receiptをResult Collectionへ渡す。
- 新GHCR digestでActionsのimage policy preflightが成功し、Jobログに
  `RTF_DATALOADER_POLICY={"num_workers":0,"pin_memory":false,"use_lhotse":false}` が出る。

## Remaining boundary

T4のbatch 8/32が物理的にOOMとなる場合、これはreceipt保証修正とは別のGPU容量制約で
あり、成功結果として扱わない。全batch完走には別GPUまたは明示的なmatrix policy変更が
必要である。

## 2026-08-23 Repository Secret 経由の再検証

対象run: [32593711141](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32593711141)

このrunはローカル`.env`をActionsへ渡さず、Repository Secretの`HF_TOKEN`をworkflowの`${{ secrets.HF_TOKEN }}`から`hf jobs run --secrets`へ伝達した。GHCR imageは次のimmutable digestで解決された。

```text
image_digest: sha256:9e697d44c6f969d50bd4c7cd3728a0806d7584be3d1525539b344c1c63ebaf08
model_revision: 44edb27eea9317daf89333e75eb830db4b1cc298
dataset_revision: bf8819e8d9a5feb51b0c718686bd20ea67a3c729
fixture_revision: 8d2c866ee315bdbed468b2e92e4587d85b6a5cc8
manifest_sha256: 9c47976f6101ebca1fc2575d46fde80d9a33dbc14b1e1f6dc2ca9aeb57a87694
```

HF Job `6a89f9577c5c7dd3792351f3`では、fixture JSONLと21音声の取得、モデル復元、content probe（`content_available=true`）まで成功した。その後、batch 1の全件推論開始時に`BENCHMARK_INFERENCE_FAILED` / CUDA illegal memory accessが発生し、metricsは生成されなかった。guarded cost policyによりbatch 8/32は`COST_GUARD_SKIPPED`となり、追加GPU費用を発生させず停止した。

ログ上、content probeは単独の`transcribe`呼出しで成功する一方、benchmark本体は同一NeMoモデルをwarmup・全件計測・repeatで再利用し、さらに本体だけautocastを有効にしていた。この実測差を原因候補として、次の修正を実装した。

- 本体の暗黙autocastを既定で無効化し、`RTF_ENABLE_AUTOCAST=1`の明示実験時だけ有効化する。
- warmupを廃止する。
- 各repeatでfixture済みsnapshotからNeMoモデルを再restoreし、推論後に破棄する。snapshot自体はHFキャッシュを使うため、再ダウンロードではない。
- GHCR cache exportは`mode=min`へ下げ、image push完了後に2.7GB級のbuild graph exportでworkflowが停滞しないようにする。

この修正後のHF/RunPod実GPU受入れは未確認であり、次の安全な単位は新digestを発行したうえで、同じHF T4 guarded batch 1を一度だけ再実行することである。

## 修正後のHF T4 guarded 実測

対象run: [32595956141](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32595956141)

新image digest `sha256:102087d0a70b2244865800604423e3089c0f872f81f98572faafbe2c914946bc`でRepository Secret経由のHF Jobを実行した。batch 1はcontent probe、全件推論、3 repeat、metrics upload、Rust benchmark record生成まで完了した。

```text
job_id: 6a8a03597c5c7dd3792352ca5
status: completed
batch_size: 1
rtfx: 95.26352914118695
rtf: 0.010497196660832634
processing_duration_sec: 56.71408616399998
peak_vram_bytes: 5606215680
metrics_sha256: 75ece9fc786fcc2afb8649057bde4a75e6f3f95f7234980c3d69ba9976ea0fe2
```

batch 8ではcontent probeは成功したが、本測定でT4の14.74 GiB中2.70 GiB freeの状態から2.71 GiB確保に失敗し、typed `BENCHMARK_INFERENCE_FAILED` / CUDA OOM receiptとなった。cost guardはbatch 32を`COST_GUARD_SKIPPED`として起動せず、追加費用を抑えた。これはbatch 1の再利用起因illegal accessとは別の、T4における長尺8件同時処理の容量制約である。

したがって現時点の受入れは、HF Secret境界、GHCR immutable image、fixture取得、content probe、batch 1 metrics/recordをcompleted、T4 batch 8/32を未成立として扱う。batch 8/32を成立させるには、別GPU lane、fixtureの長さ/バッチ契約見直し、または実効batchを変えないことを保証した長さ制御が必要であり、単純なOOM retryは行わない。

## RunPod guarded 実行境界

対象run: [32596969809](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32596969809)

Repository Secretの`RUNPOD_TOKEN`はworkflowから利用でき、`runpodctl doctor`は`healthy=true`、API key・API connectivity・SSH key同期の全てがpassした。したがってSecret権限とCLI設定は受入れ済みである。

一方、A5000 Podのbatch 1作成・接続・推論は約8分経過してもresult receiptを出力しなかったため、課金継続を避けてActionsをキャンセルした。collectにはbatch 1/8/32すべて`BENCHMARK_SETUP_FAILED`として保存され、RunPodの実GPU metricsやcontent probeは未取得である。RunPodの成功や失敗を推測せず、次回はPod create/SSH/image pullの個別時刻とremote receiptを取得できる観測を追加してから再試験する。

## RunPod引数契約の修正

上記の未成立runを再試験する前に、`scripts/run-benchmark.sh`のRunPod引数を公式CLIの契約へ合わせた。`--terminate-after`へローカルで計算したISO UTC timestampを渡す方式を廃止し、providerが解釈するduration（既定`2h`）を渡す。Podのreadiness待ちは既定20分の`RTF_RUNPOD_WAIT_TIMEOUT_MINUTES`として分離し、イメージpull・Pod起動・SSH準備の時間を含めて調整可能にした。既存の作成失敗時の名前検索、EXIT時delete、metrics/receipt回収後の即時deleteは維持する。

この変更はRepository Secretの利用方式を変更しない。GitHub Actionsでは`HF_TOKEN: ${{ secrets.HF_TOKEN }}`および`RUNPOD_TOKEN: ${{ secrets.RUNPOD_TOKEN }}`をworkflow stepのenvへ注入し、`run-benchmark.sh`へ渡す。ローカル`.env`やtoken値をActionsへコピーしない。次のRunPod guarded試験はこの引数修正を含むimageで一度だけ行い、Pod create、SSH接続、remote content probe、receipt、metrics URI/SHAを個別に確認する。
