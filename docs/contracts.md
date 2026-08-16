# Contracts

## Contractの分類

このrepositoryでは、JSONを「全部同じ設定ファイル」として扱わない。誰がauthorするかで分類する。

### Human-authored

人間が意図を指定する最小入力。

- candidate `metadata.json`
- revision `reference.json`
- `evaluation-schema.json`
- `datasets-lock.json`
- workflow dispatch inputs

human-authored入力へhash、size、runtime tensor binding、candidate IDなどの生成可能情報を書かない。

### Source-controlled generated

repositoryのcatalog等から決定的に生成され、commitされるもの。

- revision `runtime.json`
- catalog fingerprint
- schema files

### Runtime generated evidence

実行結果としてしか成立しないもの。

- `resolved.json`
- generated candidate contract
- `run-context.json`
- `metrics.json`
- `samples.jsonl`
- `nemo-onnx-validation.json`
- `nemo-reference-quality.json`
- `quality-samples.jsonl`
- `quality-comparison.json`

これらを人手で穴埋めしてPASSさせない。

## NeMo reference contract

Python producerとRust consumerの境界は`evaluation/schemas/nemo-reference-quality.schema.json`で固定する。Python側ではschemaだけでなく`parakeet_onnx.nemo.parse_reference_document()`によるtyped semantic validationも行う。

必須source identity:

```json
{
  "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
  "revision_resolved": "<immutable-hex>",
  "model_file": "parakeet-tdt_ctc-0.6b-ja.nemo",
  "model_file_sha256": "<64-lowercase-hex>",
  "library": "nemo",
  "language": "ja",
  "license": "cc-by-4.0"
}
```

sampleは次だけを持つ。

```json
{
  "id": "...",
  "audio_sha256": "...",
  "reference_text": "...",
  "text": "...",
  "normalized_text": "..."
}
```

NeMo producerはCER/WERを書かない。品質scoreはRustで再計算する。

## Normalization contract

`normalization = "asr_metrics_v1"`は以下を意味する。

```text
Unicode NFKC
→ split_whitespace
→ single ASCII space join
```

Pythonは同じ規則で`normalized_text`を生成するが、Rust consumerはそれを再計算して一致を検証する。producerが保存した正規化文字列をauthorityにしない。

## NeMo→ONNX validation contract

`nemo-onnx-validation.json`は「exportできた」ではなく、candidate化前に必要な証拠をまとめる。

主要領域:

- exact source identity
- Python/NeMo/Torch/ONNX/ORT version
- exporter/opset/dynamo情報
- checkpointから解決したfrontend/model semantics
- artifact role/path/SHA256/size/external data
- ordered gates
- known obstacle checks

CTC scopeでは少なくとも次のgateをPASSさせる。

```text
source_manifest
nemo_load
frontend_fixture
ctc_export
ctc_onnx_check
ctc_ort_cpu
ctc_reference_parity
```

TDT scopeでは追加でpredictor/joint/state traceを要求する。

## Quality comparison contract

`quality-comparison.json`はRust `asr-eval nemo-onnx-quality`だけがauthoritative producerとなる。

品質値:

```text
NeMo CER/WER
ONNX CER/WER
CER regression = ONNX CER - NeMo CER
WER regression = ONNX WER - NeMo WER
normalized transcript match rate
```

acceptance thresholdはcallerが明示する。repositoryが根拠なくdefault regression toleranceを推測しない。

## Nullとunknown fields

identity/evidence contractでは`null`を「不明」の表現として多用しない。必要な証拠がない場合は、そのcontractを生成可能な状態ではないとしてfailさせる。

NeMo referenceはunknown fieldをrejectする。Rust validation contractも`deny_unknown_fields`を使用する。将来fieldを追加する場合はschema version/consumer更新とセットで行う。

## Hashとpath

artifact identityは少なくともSHA256とsizeを持つ。relative pathはbundle rootからescapeしてはならない。

```text
禁止:
../model.onnx
/tmp/model.onnx
foo\\bar.onnx

許可:
ctc/model.onnx
tdt/encoder.onnx
fixtures/reference.npz
```

external ONNX dataも独立artifactとしてhash/sizeを検証する。
