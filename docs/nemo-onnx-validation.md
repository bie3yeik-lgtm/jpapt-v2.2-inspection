# NeMo → ONNX Validation

## 目的

`nvidia/parakeet-tdt_ctc-0.6b-ja` を NeMo reference から ONNX deployment candidateへ変換するとき、`export()` が例外なく終了したことを成功条件にしないための検証構造です。

このrepositoryでは責務を次のように分けます。

```text
Hugging Face Model Repo
  nvidia/parakeet-tdt_ctc-0.6b-ja
          ↓ exact revision
NeMo / PyTorch export-reference environment
          ↓
ONNX graph(s) + tokenizer + fixtures + evidence
          ↓
nemo-onnx-validation.json
          ↓
Release Rust CLI
  asr-eval nemo-onnx-validate
          ↓
CTC acceptance
          ↓
TDT acceptance
          ↓
normal candidate publication/evaluation
```

NeMo/PyTorchはexportとsemantic reference専用です。production validationの最終判定はRustが行います。

## Source facts

Model Cardから固定する事実は `config/conversion/parakeet-tdt_ctc-0.6b-ja.json` に集約します。

- repository: `nvidia/parakeet-tdt_ctc-0.6b-ja`
- task: `automatic-speech-recognition`
- library: `nemo`
- language: `ja`
- license: `cc-by-4.0`
- training dataset identity: `reazon-research/reazonspeech`
- architecture: Hybrid FastConformer-TDT-CTC
- input: 16 kHz mono audio
- FastConformer downsampling: 8x
- tokenizer: SentencePiece, 3072 tokens
- default decoder: TDT
- alternate decoder: CTC
- TDT can advance up to 4 frames by duration output

Model Cardにない実装値をここから推測しません。次はexact `.nemo` checkpointからexport時に解決してreportへ保存します。

- `n_mels`
- normalization
- dither
- `xscaling`
- CTC blank ID
- exact TDT duration vocabulary
- predictor h/c state shape
- ONNX tensor names and shapes

## なぜCTCから始めるか

Hybrid modelの共有Encoderを検証する最短経路だからです。

```text
NeMo frontend fixture
  ↓
FastConformer + CTC head
  ↓
model.onnx
  ↓
ORT CPU
  ↓
frame argmax
  ↓
collapse adjacent
  ↓
remove blank
  ↓
SentencePiece decode
```

CTCにstateful Predictorはありません。CTC parityが成立する前にTDTへ進むと、Encoder問題とTDT state問題を分離できなくなります。

## Canonical artifact boundary

### CTC

```text
primary      model.onnx
             + optional ONNX external data

tokenizer    revision-locked SentencePiece/tokens artifact

fixture      NeMo feature/reference output fixture
```

canonical graphにPCM→STFT→Melを含めません。NeMo complex STFT export障害とfrontend差分をgraphから分離するためです。

### TDT

```text
encoder.onnx
predictor.onnx
joint.onnx
+ external data if present
+ tokenizer
+ state-trace fixture
```

Neural network computationをONNXへ置き、token loop、duration advance、Predictor h/c state、loop guardはruntime semanticsとして扱います。

## Validation report

bundle rootに必ず次を置きます。

```text
nemo-onnx-validation.json
```

schemaは:

```text
evaluation/schemas/nemo-onnx-validation.schema.json
```

RustではJSONを一度`Value`として読み、recursive null rejectionを行ったあと`#[serde(deny_unknown_fields)]`のtyped contractへdeserializeします。

reportには次を含めます。

```text
source
  repo_id
  requested/resolved revision
  Model Card identity
  source .nemo SHA256

environment
  Python
  NeMo
  PyTorch
  ONNX
  ONNX Runtime
  opset
  exporter
  dynamo flag

resolved_model
  checkpointから取得したruntime-critical facts

frontend
  NeMo fixture parity

artifacts
  role/path/SHA256/size
  ONNX external data dependency

gates
  CTC/TDT段階別acceptance

obstacles
  既知障害ごとの検出結果とevidence
```

## Gate order

順序は固定です。

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
tdt_export
  ↓
predictor_state_parity
  ↓
joint_parity
  ↓
tdt_single_step_parity
  ↓
tdt_state_trace_parity
```

`--require ctc` は `ctc_reference_parity` までをすべて `passed` にする必要があります。後続TDT gateは `passed`, `blocked`, `not_run` を許可します。

`--require tdt` は全gateを `passed` にする必要があります。

## 既知障害をchecklist化する

adviceで事前調査した障害はreportの`obstacles`として必須化しました。

| ID | 検査意図 |
|---|---|
| `A-01-dynamo-dynamic-shapes` | Dynamo exporterとdynamic shape APIの世代差 |
| `A-02-nemo-pytorch-exporter-generation` | NeMo/PyTorch/ONNX exporter組合せ |
| `B-01-complex-stft-externalized` | complex STFTをcanonical ONNXから除外 |
| `B-02-mel-count-from-upstream` | 80/128 melをモデル名から推測しない |
| `B-03-feature-parity` | 同一PCMからNeMo feature fixtureを比較 |
| `B-04-dither-determinism` | correctness fixtureの非決定性検出 |
| `C-01-xscaling-from-upstream` | `xscaling`をcheckpointから取得 |
| `C-02-optimization-numeric-drift` | graph optimization/fusion差を区別 |
| `D-01-ctc-blank-from-upstream` | blank IDをvocab sizeから雑に推測しない |
| `E-01-predictor-state-shape` | TDT h/c rank/layoutを固定 |
| `F-01-duration-zero-loop-guard` | duration=0で無限loopしない |
| `G-01-tokenizer-revision-lock` | tokenizerをsource revisionへ固定 |
| `I-01-ort-session-load` | canonical FP32をORT CPUでload/run |
| `K-01-external-data-complete` | `.onnx.data`等をbundleから落とさない |
| `K-02-artifact-sha256-complete` | 全artifactをhash/sizeで固定 |

Rust validatorは15 IDが完全一致することを要求します。未知ID追加や必須ID欠落を黙って受理しません。

## sherpa-onnx recipeとの関係

日本語Parakeetの成熟事例では概ね次のsequenceが使われています。

```text
ASRModel.from_pretrained / restore
  ↓
model vocabularyからtokens materialize
  ↓
change_decoding_strategy("ctc")
  ↓
eval()
  ↓
set_export_config({"decoder_type": "ctc"})
  ↓
model.export(..., opset=18)
  ↓
ORT test
```

このrepositoryも同じsemantic boundaryを採用しますが、次を追加します。

- source revisionを先にimmutable commitへ解決
- `.nemo`自体のSHA256を保存
- canonical FP32を先にaccept
- frontend fixtureを別gate化
- external dataをmanifest化
- known obstacle evidenceを必須化
- Rust側でbundle実ファイルを再hash

INT8はcanonical exportではありません。FP32 acceptance後の派生candidateです。

## Hugging Face Jobsの役割

GPUが必要なNeMo export/reference workloadはHF Jobs側で実行します。Jobs側はbundleをtarget Bucketのtemporary/export prefixへ保存します。

Parakeet targetのBucketはsource-controlled target設定では:

```text
gawohok7/jpapt-v2.2-dev-bucket
```

を使用します。

推奨prefix:

```text
tmp/nemo-onnx-validation/<run-id>/
```

prefixは正式candidate IDではありません。Rust acceptance後、既存central allocator/publish flowで初めてcandidateへ昇格します。

## GitHub Actions

`.github/workflows/nemo-onnx-validation.yml` はHF Jobsが生成したbundleを検証するmanual workflowです。

入力:

- `bucket_id`
- `bundle_prefix`
- `require`: `ctc` / `tdt`
- `confirmation`

confirmationは完全一致:

```text
<bucket_id>:<bundle_prefix>:<require>
```

workflowはbundleを新規生成・修復しません。指定prefixをdownloadし、release buildしたRust CLIで検証するだけです。

```bash
asr-eval nemo-onnx-validate \
  --report <bundle>/nemo-onnx-validation.json \
  --bundle-root <bundle> \
  --require ctc
```

## Artifact integrity

Rustはreportに記載された各artifactについて実ファイルを再検査します。

- relative safe path
- regular file existence
- root escape禁止
- exact size
- exact SHA256
- external dataのexistence/size/SHA256
- duplicate path禁止
- duplicate semantic role禁止（fixtureを除く）

CTCでは最低でも `primary`, `tokenizer`, `fixture` を要求します。

TDTではさらに `encoder`, `predictor`, `joint` を要求します。

## Acceptanceとcandidate publicationを分離する

```text
HF Job export evidence
        ↓
Rust nemo-onnx-validate
        ↓
PASS
        ↓
central allocator
        ↓
minimal candidate metadata
        ↓
normal evaluator / provider matrix
```

exportが成功しただけではcandidateを発行しません。

## 現段階の意味

この構造の実装は「Parakeet TDTがRust production runtimeですでに完成した」という意味ではありません。

- CTC: Rust runtimeの最初のproduction target
- TDT: export/state parity contractを先に固定し、その後runtime controllerを完成させる

TDTについてPredictor/Joint ONNXが存在しても、state trace gateを通らない限り`--require tdt`は成功しません。
