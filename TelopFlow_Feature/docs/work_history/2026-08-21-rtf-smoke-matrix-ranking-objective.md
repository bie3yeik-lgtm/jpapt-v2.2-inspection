# RTF smoke matrix / top-3 ranking 目的の確定

## 目的

0〜100 users規模の初期サービス選定を目的に、`Calculare-RTF-Score.md`の最終表にある全有効
組み合わせを`batch=1/8/32`でsmoke測定し、最後に上位3位を自動作成する方針を記録した。

## 実装目標

- service/GPU、model、互換decoder、dataset、precision、batchをmatrix軸として扱う。
- 有効組み合わせのみを実行し、OOM・timeout・metrics欠落は成功扱いにしない。
- 完成recordだけをRust contractで検証・sortし、top-3 JSON/Markdownを生成する。
- 得られた最適サービスを、後続のbootstrap URL API配布とモデル改善実働試験の論拠にする。

## 現状確認

- `evaluation/manifests/rtf-phase1-matrix.json`は6 service/GPUとbatch 1/8/32を定義。
- `rtf-benchmark-run.yml`は一回のprovider実行でbatch 1/8/32を処理。
- 全dataset・全valid model/decoderの直積dispatch、期待cell欠落検知、top-3明示出力は未完成。

## Evidence

- Source/static: `docs/Calculare-RTF-Score.md`、matrix、benchmark/ranking workflowを確認。
- 未検証: HF Jobs / RunPodの全外部実測、最適サービス、top-3実データ。

## 次の安全な作業

Rust/schemaを正本として期待matrixとrecord identityの完全性検証を追加し、その後Actionsの
dispatch/collection/rankingを接続する。ローカルGPU smokeは実施しない。
