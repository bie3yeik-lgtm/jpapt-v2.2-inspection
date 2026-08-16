# Architecture

## 目的

このrepositoryはASRモデルを単にONNXへ変換するためのコード置場ではない。source model、dataset、変換環境、runtime artifact、evaluation result、provider evidenceを再現可能なidentity chainとして固定し、変換前後の品質とruntime成立性を別々に検証するためのinspection repositoryである。

対象となる主モデルは`nvidia/parakeet-tdt_ctc-0.6b-ja`である。Model Cardから固定する静的契約は次のとおり。

```text
repo       nvidia/parakeet-tdt_ctc-0.6b-ja
library    nemo
language   ja
license    cc-by-4.0
dataset    reazon-research/reazonspeech
architecture hybrid FastConformer TDT-CTC
default decoder TDT
CTC decoder supported
sample rate 16 kHz
tokenizer SentencePiece
vocabulary 3072
TDT frame advance <= 4
```

`n_mels`、dither、normalize、xscaling、CTC blank ID、TDT duration vocabulary、tensor name/shapeはModel Cardから推測せず、exact checkpoint evidenceから解決する。

## 3つの実行領域

### 1. Python / NeMo environment

Pythonはsource frameworkに依存する処理を担当する。

- Hugging Face revisionのimmutable SHA解決
- `.nemo` downloadとSHA256計算
- dataset materialization
- NeMo model restore
- CTC decoderへの切替
- NeMo transcript evidence生成
- NeMo→ONNX export adapter
- frontend/reference fixture生成
- JSON Schema structural validation

PythonがASR品質のauthorityになることはない。Pythonの`character_error_rate`等はdiagnostic用途に残っていても、NeMo↔ONNX acceptanceには使わない。

### 2. Rust release CLI `asr-eval`

Rustはruntime/acceptance authorityである。

```text
asr-eval evaluate
asr-eval bucket-init
asr-eval nemo-onnx-validate
asr-eval nemo-onnx-quality
```

`nemo-onnx-quality`は既存`evaluate`を内部利用し、同じresolved manifestに対して生成ONNXを実行する。その後NeMo reference transcriptとONNX transcriptの両方を同じRust `asr_metrics`へ通す。

### 3. Hugging Face Bucket

BucketはModel Repoの代替ではない。開発中のconfig snapshot、candidate、run、benchmark、experiment/evidenceを保存する。

Model Repoは配布対象、Bucketは開発・検証証拠の保存先という責務分離を維持する。

## NeMo→ONNX identity chain

```text
HF model repo + requested revision
        ↓ resolve
immutable model commit
        ↓ download
.nemo file + SHA256
        ├───────────────┐
        ↓               ↓
NeMo reference       ONNX export
transcripts          artifacts + fixtures
        ↓               ↓
reference evidence   nemo-onnx-validation.json
        └──────┬────────┘
               ↓ exact source identity equality
        asr-eval nemo-onnx-quality
               ↓
        same resolved manifest
               ↓
        Rust CER/WER + regression
```

品質比較開始前に少なくとも以下が一致しなければならない。

- repo ID
- immutable revision
- `.nemo` filename
- `.nemo` SHA256

sample単位では次も一致させる。

- sample ID
- audio SHA256
- ground-truth text

## CTCとTDTの分離

CTCは最初のcanonical runtime/quality gateである。TDTはexport artifactとstate semanticsを先に検証する。

```text
CTC:
source → frontend → export → ORT CPU → reference parity → ASR quality

TDT:
source → export → predictor state → joint → single step → state trace
                                                ↓
                              Rust TDT runtime未成立なら品質測定しない
```

TDT export validationがPASSしても、RustでTDT文字起こしが実装済みという意味ではない。

## Runtime candidateとの境界

NeMo validation bundleはpre-candidate evidenceである。validationを通る前に正式candidate IDを発行しない。

```text
HF Job export/reference
  ↓
temporary validation bundle
  ↓
Rust validation + quality gate
  ↓
central allocator
  ↓
candidate ID
  ↓
normal evaluation / benchmark / promotion
```

この順序により、失敗exportをcandidate namespaceへ混入させない。
