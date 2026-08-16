# Central Allocator

candidate / experiment / config versionの数値suffixは人間が決めません。採番表示規則は `config/hf-allocation-catalog.json` が正本です。

## Semantic allocation key

workflow/scriptはraw prefixではなく意味キーを渡します。

```text
candidate.default
candidate.parakeet-tdt-ctc-v1
candidate.whisper-autoregressive-v1
experiment.cpu_full
experiment.cross_platform_parity
experiment.rust_eval
config.version
```

catalogがこれを表示prefixへ解決し、allocatorが衝突しない `*-NNNNNN` IDを確保します。

## Flow

```text
caller
  ↓ semantic key
HF Allocation Catalog
  ↓ prefix
hf-request-id.sh / hf-allocate-id.sh
  ↓
Central allocator workflow
  ↓
allocated ID
```

## Candidate identity

allocated candidate IDはBucket directory名が正本です。uploadのために `metadata.json` を書き換えません。fetch時は `.candidate-id` をlocal markerとして生成できます。

## Root README

allocator/update scriptはBucket root READMEのmanaged領域を更新できます。READMEの表示は補助情報でありIDの正本ではありません。

## 競合

採番は複数repositoryから同一Bucketへ要求される前提です。localで「最大番号+1」を最終確定値として決めません。
