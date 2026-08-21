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
- NeMo転写APIへ対応する場合のみ `num_workers=0`、`pin_memory=false` を渡す。
- `RTF_CUDA_DIAGNOSTICS=1` のときだけ同期CUDA診断を有効にする。
- Jobがreceiptを出せず終了した場合も、provider failureをtyped receiptとして保存する。
- metricsがない失敗をcompletedとして公開しない。
- GHCR連続Resolverとrankingの古いprofile名を現行profileへ統一する。

## Acceptance evidence

Static/unit evidence:

- `transcribe_compat`がworker/pinned-memory引数をAPI互換的に渡す。
- unsupportedなNeMo引数を渡さない。
- CUDA診断モードが同期設定を有効化する。
- illegal access/OOM/一般provider失敗を別error codeでreceipt化する。
- GHCR連続Resolverが`smoke`を渡す。

External evidence:

- 新digestを使ったHF T4 smokeでcontent probeと本測定を再確認する。
- completed時はmetrics URI/SHAとreceipt identityを確認する。
- 失敗時はJobが長時間待機せず、typed blocked receiptをResult Collectionへ渡す。

## Remaining boundary

T4のbatch 8/32が物理的にOOMとなる場合、これはreceipt保証修正とは別のGPU容量制約で
あり、成功結果として扱わない。全batch完走には別GPUまたは明示的なmatrix policy変更が
必要である。
