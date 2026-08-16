# Evaluation

## Authority

release/runtime acceptanceの正本はRust `asr-eval`である。Python evaluatorはdiagnostic/orchestration用途として残るが、NeMo↔ONNX品質acceptanceのauthorityではない。

## 通常ONNX評価

```bash
asr-eval evaluate \
  --provider cpu \
  --candidate-contract <generated-candidate.json> \
  --run-context <run-context.json> \
  --resolved-manifest <resolved-manifest.json> \
  --output <run-dir>
```

出力:

```text
<run-dir>/
├── run-context.json
├── samples.jsonl
└── metrics.json
```

resolved manifestの`audio_path`は通常file I/Oで読めるmaterialized local assetでなければならない。

## NeMo reference ↔ ONNX quality

```bash
asr-eval nemo-onnx-quality \
  --provider cpu \
  --candidate-contract <candidate-contract.json> \
  --run-context <run-context.json> \
  --resolved-manifest <resolved-manifest.json> \
  --nemo-reference <nemo-reference-quality.json> \
  --nemo-validation-report <nemo-onnx-validation.json> \
  --nemo-validation-bundle-root <bundle-root> \
  --output <quality-dir> \
  --max-cer-regression <explicit-value> \
  --max-wer-regression <explicit-value>
```

thresholdは明示入力必須である。default値を「一般的だから」という理由で決めない。

## 品質計算

Rustは各sampleについてNeMoとONNX双方へ同じ関数を適用する。

```text
CER = edit_distance(normalized reference chars, normalized hypothesis chars)
      / normalized reference char count

WER = word-level edit distance / reference word count
```

normalizationは`asr_metrics_v1`。

```text
Unicode NFKC
→ whitespace collapse
```

NeMo producerに保存された`normalized_text`もRust側で再生成して検証する。

## Aggregate semantics

現状の通常benchmarkはsuccessful sampleごとのCER/WER平均を持つ。NeMo quality comparisonも同じsample setでNeMo/ONNXそれぞれのCER/WER平均を計算し、差分を取る。

```text
cer_regression = onnx_cer - nemo_cer
wer_regression = onnx_wer - nemo_wer
```

負値はONNX側がreference NeMoより良いことを意味する。acceptanceは「回帰が最大許容値以下」で判定するため、改善は通常PASSする。

## per-sample evidence

`quality-samples.jsonl`は各sampleの比較証拠を保持する。

```json
{
  "schema_version": 1,
  "sample_id": "sample-0001",
  "audio_sha256": "...",
  "reference_text": "正解文",
  "nemo": {
    "text": "NeMo文字起こし",
    "normalized_text": "...",
    "cer": 0.01,
    "wer": 0.02
  },
  "onnx": {
    "text": "ONNX文字起こし",
    "normalized_text": "...",
    "cer": 0.01,
    "wer": 0.02
  },
  "delta": {
    "cer": 0.0,
    "wer": 0.0
  },
  "normalized_text_match": true
}
```

## comparison output

`quality-comparison.json`はaggregateとacceptanceを持つ。

```text
comparison.reference_run_id
comparison.candidate_run_id
comparison.decoder
comparison.normalization
comparison.sample_count

quality.nemo.cer/wer
quality.onnx.cer/wer
quality.regression.cer/wer
quality.normalized_text_match_rate

thresholds.max_cer_regression
thresholds.max_wer_regression

acceptance.passed
acceptance.cer_passed
acceptance.wer_passed
acceptance.failed_checks
```

## 失敗時の扱い

ONNX通常評価でsample failureが発生した場合、品質比較へ進まない。「失敗sampleを除いて残りだけ比較」する挙動は採用しない。

NeMo referenceとONNX resultのsample countが異なる場合もfailする。

## Dataset scoreとconversion regression

2種類を分けて読む。

- absolute quality: NeMo CER/WER、ONNX CER/WER
- conversion regression: ONNX - NeMo

ONNXがNeMoと同じ品質でも、NeMo自体のabsolute qualityが製品要件を満たすとは限らない。逆にabsolute CERが高いdatasetでも、conversion regressionが0なら変換忠実度は高い可能性がある。

release判断では両方を別gateとして扱う。

## TDT

現在`nemo-onnx-quality`はCTCのみ。TDT referenceを渡して「未測定だが0回帰」と扱うことはしない。Rust TDT runtime/controllerとdecoder semanticsが実装された後に同じquality contractへ拡張する。
