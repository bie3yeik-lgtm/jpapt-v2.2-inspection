# NeMo → ONNX → ASR quality pipeline

## 対象

canonical targetは`nvidia/parakeet-tdt_ctc-0.6b-ja`である。

Model Card由来で固定する値:

```text
library      nemo
language     ja
license      cc-by-4.0
dataset      reazon-research/reazonspeech
sample rate  16000
architecture hybrid FastConformer TDT-CTC
default decoder TDT
CTC decoder available
tokenizer    SentencePiece
vocab size   3072
TDT advance  <= 4 encoder frames
```

checkpointから取得すべき値を別世代モデルから推測しない。

```text
n_mels
normalize
dither
xscaling
CTC blank_id
TDT durations
predictor state shape
tensor names/shapes
```

## Pipeline全体

```text
1. exact HF model revisionを解決
2. exact .nemoを取得・SHA256計算
3. NeMo checkpointをload
4. frontend/model semanticsをcheckpointから抽出
5. CTCを先行export
6. ONNX/checker/ORT CPU/reference parity
7. NeMo CTC reference transcript生成
8. Rustでsource identityを結合
9. Rust canonical ONNX evaluate
10. RustでNeMo/ONNX双方のCER/WERを再計算
11. explicit regression thresholdでacceptance
12. 必要に応じてTDT export/state validationへ進む
13. gate通過後にcandidate allocation
```

## CTCを先にする理由

Hybrid modelでもCTCはTDTよりstate machineが単純で、encoder/frontend/exporterの問題をdecoder state問題から分離しやすい。

CTC gate順序:

```text
source_manifest
  ↓
nemo_load
  ↓
frontend_fixture
  ↓
ctc_export
  ↓
ctc_onnx_check
  ↓
ctc_ort_cpu
  ↓
ctc_reference_parity
  ↓
NeMo/ONNX ASR quality
```

前段が失敗している状態で後段の品質測定へ進まない。

## Frontend

canonical ONNX graphへcomplex STFT frontendを無理に押し込まない。

```text
PCM
 ├─ NeMo frontend ──→ reference feature fixture
 └─ runtime frontend → parity
                         ↓
                    ONNX neural graph
```

fixtureではditherなどの非決定要因を固定する。`n_mels`はcheckpointから取得し、80/128等をモデル名から推測しない。

## Export artifacts

CTC最小bundle例:

```text
ctc/
├── model.onnx
└── model.onnx.data

tokenizer/
└── tokenizer.model

fixtures/
└── ctc-reference.npz

nemo-onnx-validation.json
```

TDT bundle例:

```text
tdt/
├── encoder.onnx
├── encoder.onnx.data
├── predictor.onnx
└── joint.onnx
```

external dataはONNX本体と同じartifact contractでhash/sizeを検証する。

## Known obstacle checks

Rust validatorは既知障害をmachine-readable IDとして要求する。

```text
A-01-dynamo-dynamic-shapes
A-02-nemo-pytorch-exporter-generation
B-01-complex-stft-externalized
B-02-mel-count-from-upstream
B-03-feature-parity
B-04-dither-determinism
C-01-xscaling-from-upstream
C-02-optimization-numeric-drift
D-01-ctc-blank-from-upstream
E-01-predictor-state-shape
F-01-duration-zero-loop-guard
G-01-tokenizer-revision-lock
I-01-ort-session-load
K-01-external-data-complete
K-02-artifact-sha256-complete
```

未知ID追加、必須ID欠落、duplicate、failed statusを成功扱いしない。

## NeMo reference生成

Python packageのcanonical entrypoint:

```bash
parakeet-nemo-reference \
  --model-revision <requested-or-exact-revision> \
  --resolved-manifest <resolved-manifest.json> \
  --output <nemo-reference-quality.json> \
  --batch-size 1
```

内部では次を行う。

- `HfApi.model_info(...).sha`でimmutable revisionへ解決
- exact revisionから`.nemo` download
- `.nemo` SHA256計算
- `ASRModel.restore_from`
- `change_decoding_strategy(decoder_type="ctc")`
- manifest内audio SHA256を実fileから再計算
- `model.transcribe`
- transcript evidence生成

reference run IDはmodel revisionだけでなくsample-set digestも含む。

```text
nemo-<revision-prefix>-ctc-<sample-set-digest-prefix>
```

これにより同じcheckpointでも別manifestを同一reference runとして扱わない。

## PythonはCER/WER authorityではない

NeMo producerはtranscriptだけを生成する。

```text
Python:
reference_text + NeMo text + normalized text + provenance

Rust:
CER/WER(NeMo)
CER/WER(ONNX)
regression
acceptance
```

Python側で計算済みmetricをJSONへ保存してRustが読む設計は採用しない。

## Source identity binding

`asr-eval nemo-onnx-quality`は品質測定の前に既存`nemo-onnx-validate`相当をCTC scopeで実行する。

そのvalidation reportとNeMo referenceで、以下を完全一致させる。

```text
repo_id
revision_resolved
model_file
model_file_sha256
```

これが一致しなければONNX推論自体を開始しない。

## Sample identity binding

sampleごとに次を一致させる。

```text
sample ID
audio SHA256
ground-truth text
```

配列順だけでNeMo出力とONNX出力を対応付けない。

## TDT

TDTでは以下を別gateとして検証する。

```text
tdt_export
predictor_state_parity
joint_parity
tdt_single_step_parity
tdt_state_trace_parity
```

特にduration=0時のloop guardとpredictor state更新を検証する。

ただし、Rust TDT runtime/controllerが実装されるまではTDT ASR品質測定対応を主張しない。TDT export/state validation PASSと、TDT文字起こし品質PASSは別物である。
