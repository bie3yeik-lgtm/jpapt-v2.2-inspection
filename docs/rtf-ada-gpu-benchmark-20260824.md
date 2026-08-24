# RTF benchmark: RTX 2000 Ada / RTX 4000 Ada

## 結論

RTX 2000 AdaとRTX 4000 Adaは、ParakeetのCUDA FP16推論を比較するGPUとして追加する。
ただし、HF JobsのflavorではなくRunPod PodのGPU候補としてのみ扱う。

RunPod公式のGPU一覧には、次のGPU typeが掲載されている。

```text
NVIDIA_RTX_2000_ADA_GENERATION -> NVIDIA RTX 2000 Ada Generation
NVIDIA_RTX_4000_ADA_GENERATION -> NVIDIA RTX 4000 Ada Generation
```

workflow内部の短縮IDは次のとおりとする。

```text
rtx2000-ada -> NVIDIA RTX 2000 Ada Generation
rtx4000-ada -> NVIDIA RTX 4000 Ada Generation
```

## Adaとは何か

AdaはNVIDIAのGPUアーキテクチャ世代名であり、ParakeetやNeMoのモデル名ではない。
RTX 2000 Ada、RTX 4000 Ada、L4、RTX 4090などはAda Lovelace世代に属する。
世代が同じでもGPU製品ごとのCUDA core数、VRAM、メモリ帯域、電力枠は異なるため、
「Adaだから同じ性能」とは扱わない。

## Parakeetへの適合性

- CUDA実行環境であり、既存のParakeet benchmark imageと`precision=float16`の境界に適合する。
- RTX 2000 Adaは16GB級のため、Parakeet本体・NeMo・音声データ・batch 32の組み合わせでは
  VRAM不足になり得る。まずbatch 1、次にbatch 8、最後にbatch 32を順に試す。
- RTX 4000 AdaはRTX 2000 Adaより大きいメモリ余裕を持つ候補だが、実際の利用可能VRAMは
  RunPodのGPU typeとイメージのCUDA runtimeで確認する。OOMしないことは事前に仮定しない。
- OOM、CUDA illegal access、Pod作成不可はcompleted metricsとせず、blocked receiptとして保存する。

## 実装上の責務

- `rtf-benchmark-run.yml`と`rtf-verification-select.yml`に選択肢を追加する。
- `scripts/run-benchmark.sh`でRunPodの正式GPU名へ変換する。
- Rust cost policyでRunPod専用GPUとして受け入れる。
- Phase 1 matrixへbatch `1/8/32`のエントリを追加する。
- result collectionではmetricsに記録された実GPU名・料金・VRAMを正本とし、短縮IDから性能値を推測しない。

## 参照

- [RunPod GPU types](https://docs.runpod.io/flash/configuration/gpu-types)
- [RunPod RTX 2000 Ada](https://www.runpod.io/gpu-models/rtx-2000-ada)
- [NVIDIA RTX 2000 Ada](https://www.nvidia.com/en-us/geforce/news/gfecnt/20242/rtx-2000-ada/)
- [NVIDIA RTX 4000 Ada](https://www.nvidia.com/en-us/products/workstations/rtx-4000/)
