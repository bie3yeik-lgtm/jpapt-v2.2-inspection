# ONNX Export

Exportの成果物は、runtimeが後から検査可能なONNX graph・tokenizer/model config・minimal `metadata.json` です。

ただし **export成功はcandidate acceptanceではありません**。特にNeMo/Parakeetでは、exporterがファイルを生成しただけではfrontend、Encoder、CTC blank、TDT state、external dataのsemantic correctnessを証明できません。

## Flow

通常のcandidate flowは次です。

```text
upstream/reference model
  ↓ export
ONNX graph(s) + generated config/tokenizer assets
  ↓ validation / reference parity
accepted export bundle
  ↓ finalize_candidate_variant()
minimal metadata.json
  ↓ CandidateArtifacts.load()
strict graph/config inspection
  ↓
resolved runtime contract
```

`nvidia/parakeet-tdt_ctc-0.6b-ja` のNeMo exportでは、`validation / reference parity` が [nemo-onnx-validation.md](./nemo-onnx-validation.md) の専用gateです。

```text
NeMo exact revision
  ↓
FP32 export + NeMo fixtures
  ↓
nemo-onnx-validation.json
  ↓
asr-eval nemo-onnx-validate --require ctc
  ↓
CTC accepted
  ↓
必要なら TDT artifact/state parity
  ↓
asr-eval nemo-onnx-validate --require tdt
  ↓
finalize / candidate publication
```

## Artifact roles

- CTC runtime candidate: `primary`
- TDT runtime candidate: `encoder`, `predictor`, `joint`
- Whisper: `encoder`, `decoder`, optional `decoder_with_past`

roleの意味と必須/任意関係は `config/asr-catalog.json` が正本です。

NeMo export validation bundleはcandidate metadataより広い証拠集合を持ちます。CTCでは少なくとも `primary + tokenizer + fixture`、TDT validationではさらに `encoder + predictor + joint` を要求します。このvalidation bundleをそのままcandidate metadataとして扱ってはいけません。

## NeMo Parakeetのcanonical boundary

Canonical FP32 ONNXにはPCM frontendを含めません。

```text
PCM
 ↓
NeMo-compatible STFT / Mel / normalization
 ↓                    ↑
fixture parity        │ outside ONNX
 ↓
FastConformer + CTC head
 ↓
CTC ONNX
```

理由は、complex STFT export問題とfrontend numerical driftをEncoder graph問題から切り離すためです。

TDTではneural graphとdecoding controllerを分離します。

```text
encoder.onnx
predictor.onnx
joint.onnx
      ↓
Rust/runtime controller
  token state
  LSTM h/c
  encoder position
  duration advance
  loop guards
```

## Model Card値とcheckpoint値

Model Cardに明記された値と、checkpointからのみ得られる値を混同しません。

Model Cardから固定できる例:

- NeMo model
- Japanese ASR
- 16 kHz mono
- Hybrid FastConformer-TDT-CTC
- 8x encoder downsampling
- SentencePiece 3072 tokens
- default TDT / alternate CTC
- TDT durationで最大4 frame skip

checkpointから実測するもの:

- `n_mels`
- `normalize`
- `dither`
- `xscaling`
- CTC blank ID
- exact TDT duration vocabulary
- Predictor state shape
- actual ONNX I/O names/shapes

後者をモデル名、別世代Parakeet、既存コードの定数から推測してはいけません。

## metadata生成

finalize処理はcandidate構成をminimal metadataへ統合します。hash、size、candidate ID、decoder config、tensor bindingをhuman-authored metadataへ焼き込みません。

NeMo validationのartifact hash/sizeは `nemo-onnx-validation.json` に生成証拠として保存され、Release Rust CLIが実ファイルを再hashします。candidate publication時には既存のgenerated candidate contractへ再解決します。

## Generated config

runtime inspectionが意味を一意に取得できるよう、exporterは必要なmodel/tokenizer factsをgenerated configまたはONNX metadataとして残します。特にTDTのBOS/durations/static predictor state、Whisperのprompt/eos等は推測に依存させません。

## External data

0.6B級graphではONNX weightがexternal dataへ分離される可能性があります。

```text
model.onnx
model.onnx.data
```

または同等のweight fileを**1つのartifact bundle**として扱います。`.onnx`だけをhash/publishしてexternal dataを落とすcandidateはrejectします。

## `runtime-contract.json`

human-authored inputとして使用しません。runtime contractは実artifactを検査して生成します。

## Validation

exportが成功してもcandidate成立とは限りません。

Parakeet NeMo exportでは最低でも:

1. exact upstream revision
2. NeMo load
3. frontend fixture
4. CTC FP32 export
5. ONNX structural check
6. ORT CPU execution
7. NeMo CTC parity
8. artifact/external-data SHA256

を通します。TDTはその後にPredictor state、Joint、single-step、multi-step state traceを追加します。

最終的に `CandidateArtifacts.load()` によるschema、artifact role、tokenizer discovery、hash、ONNX I/O、runtime-critical metadataのstrict validationを通過して初めて通常評価対象になります。
