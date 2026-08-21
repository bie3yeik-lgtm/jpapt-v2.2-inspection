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
