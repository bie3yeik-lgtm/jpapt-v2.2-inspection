# RTF smoke matrix と上位3位ランキングの着手契約

更新日: 2026-08-21
状態: 0〜100 users向け初期サービス選定の実装目標

## 目的

`docs/Calculare-RTF-Score.md`の「最終的に作るべき表」に記載された全ての有効な組み合わせを、
`batch=1/8/32`でsmoke測定する。測定結果から自動的に上位3位を作成し、最適サービス選定の
論拠とする。

この成果を根拠に、後続でbootstrap URLによるAPI配布と、モデル改善の実働試験へ進む。

## 期待するmatrix

| 軸 | 期待値 |
|---|---|
| service/GPU | HF Jobs: T4/L4、RunPod Pod: A5000/L4/RTX 3090/RTX 4090 |
| model | Parakeet TDT-CTC、Kotoba Whisper |
| decoder | modelと互換なdecoderのみ |
| dataset | Common Voice Japanese、JSUT Basic 5000、ReazonSpeech test |
| batch | 1、8、32 |
| profile | `smoke`（HF/RunPodの現行実行profile） |
| repeat | matrix軸ではなくrunner内で固定管理 |

モデル・decoderの有効組み合わせを3通りとした場合、期待record数は
`6 × 3 × 3 × 3 = 162`である。matrix変更時はこの値を自動計算し、手書きの件数を正本にしない。

## 受入条件

1. resolverが固定fixture、manifest SHA、revisionを全cellへ同一契約で渡す。
2. GHCR imageはdigest固定で全cellが同一実行環境を参照する。
3. 各cellでbatch 1/8/32のreceiptを生成する。
4. OOM、timeout、provider error、metrics欠落は`blocked`または`not_verified`として保持する。
5. completed recordはresult/metrics SHA、provider execution proof、CER、RTF、costを持つ。
6. 期待cellの欠落、重複identity、manifest/image/provider不一致をranking前に拒否する。
7. Rustのranking contractでcompleted recordを決定的にsortし、上位3位をJSON/Markdownへ出力する。
8. top-3にはservice、GPU、model、decoder、dataset、batch、RTF、CER、`$/audio-hour`を含める。

## ランキングから後続試験へ

```text
all valid cells measured
  -> Rust validation
  -> top 3 ranking
  -> selected service / GPU
  -> bootstrap URL API distribution
  -> model improvement live trial
```

ランキングはサービスの性能・コスト比較の根拠であり、API配布の可用性やモデル改善効果を
自動的に証明しない。後続試験では別のrun identity、revision、受入条件を持たせる。

## 現在の差分と次の作業

- 現在のmatrix定義はservice/GPUとbatchを持つが、全dataset・全valid model/decoderの一括dispatchは未完成。
- ranking workflowはprofile配下のrecordを収集するが、期待cellの完全性検証とtop-3制限を追加する必要がある。
- 外部HF Jobs / RunPod実測なしでは最適サービスを決定しない。
- ローカルGPU smokeは実施せず、Rust/schema/workflow contract検証を先行する。
