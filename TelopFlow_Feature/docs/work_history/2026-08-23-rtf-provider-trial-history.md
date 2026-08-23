# Work history: RTF provider試行錯誤の統合記録

更新日: 2026-08-23

## 目的

これまでのGHCR、RTF Resolver、Hugging Face Jobs、RunPod smoke試験で発生した問題を、
provider実行境界ごとに分類し、現行仕様と次の安全な作業を一つの正本から追跡できるように
する。

## 変更範囲

- 正本: [`docs/rtf-provider-trial-history-20260823.md`](../../../docs/rtf-provider-trial-history-20260823.md)
- 本work history: 本ファイル
- 大容量model/audio/metrics本体、credential、Pod接続情報は追加しない。

## 実装・調査結果

- Resolver生成差分を失うdelivery問題をPR #438/#439で解消。
- CUDA driver compatibility、OOM、illegal accessをtyped gate/receiptへ分離。
- RunPodのenvironment転送、shell quoting、Python executable/package path、SSH key、
  runtime/SSH readiness、container log、balance/instance availabilityを別境界として整理。
- RTX 4090の`RUNPOD_NO_INSTANCE_AVAILABLE`はPod作成前の外部供給不足として記録。
- RTX 3090のAction run `32629746571`でPod作成からcontent probe、metrics、receipt、cleanup
  まで成功。

## 受入証拠

```text
Action run 32629746571: success
content_available: true
metrics status: completed
rtf: 0.002900633579646387
rtfx: 344.75226620037574
peak_vram_bytes: 5606215680
Pod cleanup: verified
worktree: clean before this documentation change
```

## 未検証・ブロッカー

- full matrix 1/8/32、全GPU比較、ranking、CER品質は未完了。
- reference textが空白のため、今回の成功runは性能・content取得の証拠であり、品質評価の
  証拠ではない。
- RunPodの供給・runtime readinessは外部状態であり、再試行はguarded batch 1から開始する。

## 次の安全な単位

1. この文書をレビュー・mergeする。
2. 成功したimmutable image/fixture identityを使ってHF/RunPodの比較を行う。
3. reference text付きfixtureを準備できた後、full matrixとrankingへ進む。

## ロールバック

本変更は文書のみであり、既存のfixture、receipt、metrics、workflow、provider Podを変更
しない。文書commitだけをrevertすれば、実行経路は変更前のままになる。
