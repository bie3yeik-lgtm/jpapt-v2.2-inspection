# Work history: authenticated RunPod RTF smoke completed

更新日: 2026-08-23

## 実行経路

PR #429をmainへmergeした後、mainのGHCR build/publishとRTF Resolverを完了し、
発行されたdigestを使ってRunPod guarded batch 1を1回実行した。

```text
ghcr_run: 32625124553
merge_commit: 075130c1477ebbb324f7f4ca998446b34976f9ce
image_digest: sha256:3ea1bc51ecbab7d5922cffb209f0e0323b9914ec1dedfb40cd82bace658abfc8
fixture_revision: 0556991b56c5f6e9753402ab2265232ce2577ae1
manifest_sha256: 9c47976f6101ebca1fc2575d46fde80d9a33dbc14b1e1f6dc2ca9aeb57a87694
run_id: rtf-runpod-local-20260823-r5-b1
pod_id: m6rgor1zyt6v5w
gpu: rtx4090
batch_size: 1
repeat: 1
inspection_profile: smoke
```

## 結果

Pod作成、private GHCR image pull、runtime initialization、SSH handshake、fixture
download、content probe、metrics execution、HF Dataset result uploadまで成功した。

content probeは次を返した。

```text
status: completed
content_available: true
fixture_revision: 0556991b56c5f6e9753402ab2265232ce2577ae1
```

metricsは次の値を返した。

```text
status: completed
audio_duration_sec: 5402.784
processing_duration_sec: 10.773018113803118
rtf: 0.0019939753493389925
rtfx: 501.5107134255709
peak_vram_bytes: 5478424576
```

`RTF_DATALOADER_POLICY`は実行ログ上で次の通り適用された。

```json
{"num_workers":0,"pin_memory":false,"use_lhotse":false}
```

Full CUDA graph compilationにはRTX4090上で`cudaErrorInvalidValue`のwarningが出たが、
native PyTorch CUDA graphへfallbackし、content probeとmetricsはcompletedになった。
`PROVIDER_CUDA_ILLEGAL_ACCESS`またはOOMは発生していない。これはwarningを成功として
隠蔽した証拠ではなく、最終receiptとmetricsがcompletedで、metricsが生成されたことを
含む実行結果として記録する。

## identityとcleanupの検証

```text
receipt.status: completed
receipt.metrics_sha256: 8a1c64cbe8968ad727ad563008fff2c5ddbd242095ee2fc9e57a10bb1ca2eb6e
receipt.result_sha256:  8a1c64cbe8968ad727ad563008fff2c5ddbd242095ee2fc9e57a10bb1ca2eb6e
local metrics SHA-256:  8a1c64cbe8968ad727ad563008fff2c5ddbd242095ee2fc9e57a10bb1ca2eb6e
result_revision: 5dbfda0ec742ace4ce2033a286d58b8bd1a92bba
post-run RunPod pod list: []
```

metrics URIは`gawohok7/rtf-benchmark-fixtures`のresult revisionへ保存された。
大容量audio、model、metrics本体はrepositoryへ追加しない。ローカルresultは既存の
`results/` ignore境界に留める。

## 判定

- local static/mock adapter verification: verified
- GHCR build/publish with package import check: verified
- RTF Resolver with new image identity: verified
- RunPod GHCR registry auth: verified
- RunPod SSH/package path: verified
- content probe: verified
- metrics and result receipt: verified
- Pod cleanup: verified
- larger matrix / ranking: not run; this was intentionally guarded batch 1

## 次の安全な作業

この成功runをsmokeの最小実行証拠として保存する。1/8/32のfull benchmark matrix、
HF Jobs比較、ranking成果PRは、同じimage/fixture identityを参照するGitHub Actionsの
RTF Benchmark Runから段階的に実行する。batch 8/32へ進む前に、batch 1のmetrics schema、
receipt SHA、result revisionをランキング入力契約へ接続する。

