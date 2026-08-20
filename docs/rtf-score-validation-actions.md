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

## 参照仕様の要約

参照ファイルは [docs/Calculare-RTF-Score.md](Calculare-RTF-Score.md) に保存する。
ブランチの実装対象は、その内容に基づく次のベンチマークである。

### RTF の定義

```text
RTF = 処理時間 / 入力音声の総再生時間
RTFx = 1 / RTF
```

主指標は個々の音声の RTF の平均ではなく、`total_processing_time /
total_audio_duration` とする。GPU の非同期実行を正しく測るため、CUDA 実行前後に
`torch.cuda.synchronize()` 相当の同期を行う。

### 固定する共通入力と比較対象

入力は 16 kHz、mono、PCM WAV に正規化し、次の 3 データセットを同じ入力として
使用する。

- `japanese-asr/ja_asr.common_voice_8_0`
- `japanese-asr/ja_asr.jsut_basic5000`
- `japanese-asr/ja_asr.reazonspeech_test`

比較対象は `nvidia/parakeet-tdt_ctc-0.6b-ja` の TDT/CTC と
`kotoba-tech/kotoba-whisper-v2.0`。Kotoba の Model Card にある `6.3x faster` は
Whisper large-v3 に対する相対値であり、実測した絶対 RTF とは別の指標として扱う。

### 測定範囲と行列

モデル比較用の `RTF_model`（モデル入力から推論完了まで）と、製品原価用の
`RTF_service`（Opus decode、resample、前処理、推論、後処理を含む）を分離する。
batch=1 の latency RTF と、batch=16/32 などの throughput RTF も分けて保存する。

最低限、GPU、provider、dtype、decoder、batch size、dataset、音声総時間、処理時間、
RTF、RTFx、CER、ピーク VRAM、GPU utilization、warm-up 回数を記録する。初期 GPU
選別は RunPod の A5000/L4/3090/4090 と HF の T4/L4 を対象に、TDT・FP16/BF16・
batch 1/8/32 で行い、上位 GPU を詳細測定へ進める。検証対象サービスは HF Inference
Endpoint、RunPod Pod、RunPod Serverless を区別し、将来 provider を追加できる形式に
する。単価を取得できる場合は
`GPU price/hour * RTF_service` で audio-hour 原価も算出する。

## 実装契約

実装はプロジェクトの Rust-first 方針に従い、算出・検証結果の正規化・JSON 永続化は
可能な限り Rust に置く。GitHub Actions YAML は実行のオーケストレーションに限定し、
候補結果が期待値・参照データを上書きしないようにする。結果にはモデル、revision、
artifact SHA-256、provider、環境、run identity、測定条件、各 dataset/decoder/batch
の測定値を含め、サービスごとの検証結果を machine-readable artifact として保存する。

実装はプロジェクトの Rust-first 方針に従い、算出・検証結果の正規化・JSON 永続化は
可能な限り Rust に置く。GitHub Actions YAML は実行のオーケストレーションに限定し、
候補結果が期待値・参照データを上書きしないようにする。結果にはモデル、revision、
artifact SHA-256、provider、環境、run identity、測定値を含め、再現可能な証拠として
保存する。

## 現時点の状態

- ブランチ: `feat/rtf-score-validation-actions`
- 実装状態: 仕様理解と測定契約の文書化済み。算出器、評価 runner、Actions は未実装
- 次のアクション: テスト先行で RTF 算出・結果 schema・サービス検証 matrix・Actions
  保存処理を実装し、固定 revision と実測証拠を添えて検証する
