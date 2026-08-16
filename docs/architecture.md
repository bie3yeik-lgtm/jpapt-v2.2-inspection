# Architecture

## 目的

このrepositoryは、ASRモデルをONNX artifactへ変換し、複数provider / evaluatorで再現可能に評価し、Hugging Face Bucket上でcandidate・run・benchmarkを履歴化するための開発基盤です。

framework差分をstorage treeやJSON schemaの分岐として増殖させず、runtime profileとadapterへ閉じ込めます。

## Source of truth

```text
Runtime semantics        config/asr-catalog.json
Allocation naming       config/hf-allocation-catalog.json
Target identity         config/hf-targets/*.toml
Evaluator capability    config/evaluators/*.toml
Provider policy         config/providers/*.toml
Environment policy      config/environments/*.toml
Evaluation policy       config/evaluation/*.toml
Candidate input         candidates/<id>/metadata.json
Candidate schema        evaluation/schemas/candidate-metadata.schema.json
Manifest schema         evaluation/schemas/manifest.schema.json
Run snapshot schema     evaluation/schemas/run-context.schema.json
```

文書はこれらの実装を説明するだけで、意味の正本にはしません。

## レイヤ

```text
Target
  ↓ profile_set
ASR Runtime Catalog
  ↓ runtime variant
Candidate artifacts
  ↓ strict inspection
Resolved runtime contract
  ↓ evaluator/provider selection
Evaluation run
  ↓
run-context + samples + metrics
  ↓
benchmark / promotion
```

### Human-authored layer

人間は「選択・policy」だけを書きます。

- target mapping
- evaluation policy
- candidateのartifact path
- manifestのdataset/count/seed/filter

### Machine-observed layer

コードが観測できる値は手書きしません。

- candidate ID
- SHA-256 / size
- catalog fingerprint
- decoder/profile/features
- ONNX tensor names / dtypes / shapes
- token IDs
- TDT durations/state metadata
- Git / host / provider runtime identity

### Immutable snapshot layer

再現性のため、実行後は観測値をsnapshotします。

- config version
- run-context
- samples
- metrics
- benchmark
- promotion receipt

## Decoder architecture

### CTC

単一ONNX graph。artifact roleは `primary`。

### TDT

複数graph。artifact roleは `encoder`, `predictor`, `joint`。

TDT contractはstrictに解決します。BOS、duration値、state shape等が明示的に得られなければrejectします。

### Whisper autoregressive

`encoder`, `decoder` と任意の `decoder_with_past`。Transformers processor/configからprompt/eos等を取得します。

## PythonとRust

Python ONNX evaluatorはCTC/TDT/Whisperを扱います。Rust ONNX evaluatorの公開capabilityは現在CTCのみです。backend/provider差分より先にdecoder capabilityを明示的にgateします。

## 禁止事項

- 旧schemaを読めるようにcompat branchを増やす
- runtime semanticsをcandidate metadataへ複製する
- ONNX shapeからtoken semanticsを推測する
- 不明値をplaceholder `1` やblank tokenで埋める
- provider/frameworkごとにBucket treeを分岐する
