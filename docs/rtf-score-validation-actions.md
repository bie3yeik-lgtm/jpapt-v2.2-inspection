# RTF スコア算出とサービス検証 Actions

## 目的

このブランチでは、指定された Premiere AutoProcess Plugin の仕様に基づく
RTF (Real-Time Factor) スコア算出機能と、仕様に列挙された全サービスの検証結果を
GitHub Actions からリポジトリへ保存する仕組みを実装する。

このリポジトリ自体の目的は、`nvidia/parakeet-tdt_ctc-0.6b-ja` を起点とした
日本語 ASR の ONNX デプロイメント成果物を開発・検証することである。ONNX は
デプロイメント成果物として扱い、モデル、プロバイダー、環境、評価設定を分離する。
評価では frontend/encoder/logits/token/text parity、ASR quality、performance、
provider fallback を別々の証拠として扱い、最終 transcript の一致だけを数値的な
正しさの根拠にしない。

## 参照仕様

指定された参照ファイル:

`https://github.com/largoyo/Premiere-AutoProcess-Plugin/blob/main/inspection/advices/Calculare-RTF-Score.md`

2026-08-20 に次の方法で取得を試みた。

| 方法 | 結果 |
|---|---|
| GitHub blob URL | `404 Not Found` |
| `raw.githubusercontent.com` URL | `404 Not Found` |
| GitHub Contents API (`inspection/advices`) | `404 Not Found` |

したがって、このコミット時点では参照ファイルの本文、RTF の計算式、測定区間、
対象サービス一覧を確認できていない。仕様を推測して実装することはしない。

## 実装契約（仕様取得後に確定）

参照ファイルが取得可能になったら、少なくとも次を本文から明示的に転記・固定する。

1. RTF の分子・分母と単位、丸め規則、無効値の扱い。
2. 音声の測定対象区間と、推論・前処理・I/O のどこを経過時間に含めるか。
3. 検証対象となる全サービス名、入力、期待結果、再試行・タイムアウト条件。
4. 結果 JSON のスキーマ、保存先、成果物名、コミットまたは artifact の保持方針。

実装はプロジェクトの Rust-first 方針に従い、算出・検証結果の正規化・JSON 永続化は
可能な限り Rust に置く。GitHub Actions YAML は実行のオーケストレーションに限定し、
候補結果が期待値・参照データを上書きしないようにする。結果にはモデル、revision、
artifact SHA-256、provider、環境、run identity、測定値を含め、再現可能な証拠として
保存する。

## 現時点の状態とブロッカー

- ブランチ: `feat/rtf-score-validation-actions`
- 実装状態: 参照仕様が取得不能のため未実装
- ブロッカー: 指定 URL が 404 で、RTF 式と全サービス一覧が不明
- 次のアクション: 正しい URL、公開されたファイル、またはファイル本文を提供し、
  その内容を固定したうえでテスト先行の算出器・Actions・保存スキーマを実装する
