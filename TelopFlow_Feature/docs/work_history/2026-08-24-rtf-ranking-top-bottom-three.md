# RTF ranking top/bottom three display

## 目的

RTF rankingのMarkdown成果物で、最上位3件だけでなく、同じRust rankerの
決定的な並び順に基づく下位3件も表示する。

## 変更

`.github/workflows/benchmark-ranking.yml`の表示生成だけを変更した。
`rtf-scores/ranking.json`は従来どおり全ての受入れ済みrecordを保持し、Rustの
ランキング契約・比較順・最新completed record選択は変更していない。

recordが3件以下の場合、同じrecordをTop/Bottomへ重複表示しない。

## 検証

- workflow YAML構造確認
- `git diff --check`
- Top/Bottomのslice式と少数record時の重複防止を静的確認

provider実行や外部サービスへのbenchmark実行はこの表示変更の検証対象外。
