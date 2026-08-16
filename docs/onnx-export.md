# ONNX Export

Exportの成果物は、runtimeが後から検査可能なONNX graph・tokenizer/model config・minimal `metadata.json` です。

## Flow

```text
upstream/reference model
  ↓ export
ONNX graph(s) + generated config/tokenizer assets
  ↓ finalize_candidate_variant()
minimal metadata.json
  ↓ CandidateArtifacts.load()
strict graph/config inspection
  ↓
resolved runtime contract
```

## Artifact roles

- CTC: `primary`
- TDT: `encoder`, `predictor`, `joint`
- Whisper: `encoder`, `decoder`, optional `decoder_with_past`

roleの意味と必須/任意関係は `config/asr-catalog.json` が正本です。

## metadata生成

finalize処理はcandidate構成をminimal metadataへ統合します。hash、size、candidate ID、decoder config、tensor bindingをmetadataへ焼き込みません。

## Generated config

runtime inspectionが意味を一意に取得できるよう、exporterは必要なmodel/tokenizer factsをgenerated configまたはONNX metadataとして残します。特にTDTのBOS/durations/static predictor state、Whisperのprompt/eos等は推測に依存させません。

## `runtime-contract.json`

human-authored inputとして使用しません。runtime contractは実artifactを検査して生成します。

## Validation

exportが成功してもcandidate成立とは限りません。`CandidateArtifacts.load()` によるschema、artifact role、tokenizer discovery、hash、ONNX I/O、runtime-critical metadataのstrict validationを通過して初めて評価対象になります。
