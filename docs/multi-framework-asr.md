# Multi-framework ASR

framework名ではなくruntime profileを中心に扱います。Bucket layoutやcandidate schemaはNeMo/Transformersで分岐しません。

## Runtime profiles

`config/asr-catalog.json` が正本です。

### `ctc-v1`

```text
decoder            ctc
artifact contract  ctc-single-graph-v1
artifact roles     primary
tokenizer          vocabulary
```

CTC runtime contractはONNX graphからaudio/input length/logits bindingを検査し、blank IDはgenerated config・ONNX metadata・vocabularyから取得します。

### `tdt-v1`

```text
decoder            tdt
artifact contract  tdt-multi-graph-v1
artifact roles     encoder / predictor / joint
tokenizer          vocabulary
```

TDTはmulti-graph contractです。encoder/predictor/joint I/O、predictor state、blank/BOS、duration値をstrictに取得します。不明値をshapeから推測しません。

### `whisper-autoregressive-v1`

```text
decoder            whisper_autoregressive
artifact contract  whisper-autoregressive-v1
required roles     encoder / decoder
optional role      decoder_with_past
tokenizer          transformers_processor
```

prompt/eos/suppress token、decoder/KV bindingはgenerated Transformers configとONNX graphから解決します。

## Profile sets

```text
parakeet-tdt-ctc-v1
  ctc -> ctc-v1
  tdt -> tdt-v1
  default = ctc

whisper-autoregressive-v1
  whisper -> whisper-autoregressive-v1
  default = whisper
```

Parakeet上流がTDT-CTC hybridであることと、このrepositoryのdeployment defaultがCTCであることは別概念です。

## Evaluator capability

Python ONNX evaluatorはCTC/TDT/Whisper autoregressiveを公開します。Rust ONNX evaluatorは現在CTCだけを公開します。対応範囲は `config/evaluators/*.toml` でgateし、実装されていないdecoderをprovider側で暗黙fallbackさせません。
