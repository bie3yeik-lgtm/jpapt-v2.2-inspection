# Architecture

## 1. 目的

このrepositoryは、日本語ASRモデルをONNXへ変換・検証し、Execution Providerごとの正確性・性能・provider利用実態を同一contractで比較するための開発基盤です。

設計上の最重要原則は、**人が意味を推測してJSONへ写経しないこと**です。runtime-criticalな値はcatalog、実artifact、tokenizer/config、revision lockから生成し、一意に決められない場合はfailします。

## 2. Source of truth

### Repository側

- `config/asr-catalog.json`
  - decoder profile
  - artifact role
  - tokenizer kind
  - feature capability
  - profile set / variant mapping
- `config/hf-allocation-catalog.json`
  - candidate / experiment / config versionの採番prefix
- `config/hf-targets/*.toml`
  - upstream、framework、profile set、実HF Bucket、Model Repo
- `config/models/*.toml`
  - model execution compatibility
- `config/providers/*.toml`
  - ORT provider/session条件
- `config/environments/*.toml`
  - OS/environment条件
- `config/evaluation/*.toml`
  - smoke/parity/full等の評価条件
- `evaluation/schemas/*.schema.json`
  - persisted JSON/JSONL artifactsの構造contract

### HF Bucket側

- `config/versions/config-NNNNNN/`
  - immutable revision-lock bundle
- `config/current.json`
  - 現在選択されるconfig versionへのpointer
- `candidates/<candidate-id>/`
  - development candidate artifact
- `runs/<run-id>/`
  - 完全な評価履歴
- `benchmarks/<candidate-id>/<benchmark-name>/<run-id>.json`
  - 軽量なmetrics index
- `experiments/<experiment-id>/`
  - 中央Allocator管理のexperiment namespace

### HF Model Repo側

accepted candidateをpromotionした最終成果物を置きます。Bucketは開発・検証用のmutable object storage、Model Repoはversioned release historyとして役割を分離します。

## 3. データライフサイクル

```text
upstream HF model
      |
      v
export / finalize
      |
      v
local candidate directory
  metadata.json            # human-authored minimal intent
  *.onnx / tokenizer/...   # actual artifacts
      |
      | CandidateArtifacts.load()
      | graph/tokenizer inspection
      v
generated candidate contract
      |
      +------------------------------+
      |                              |
      v                              v
Python evaluator                 Rust evaluator
CTC/TDT/Whisper                  CTC
      |                              |
      +--------------+---------------+
                     v
               run-context.json
               samples.jsonl
               metrics.json
                     |
                     v
             HF Bucket runs/<run-id>
                     |
             accepted full evaluation
                     |
                     v
          HF Model Repo promotion
```

## 4. Candidate boundary

candidate directoryのhuman-authored contractは `metadata.json` だけです。

```text
candidate/
├── metadata.json
├── ctc/
│   └── model.onnx
├── tdt/
│   ├── encoder.onnx
│   ├── predictor.onnx
│   └── joint.onnx
└── tokenizer/
    └── vocabulary.json
```

`.candidate-id` はBucketからfetch後にmaterializeされるidentity markerであり、publish前のsource candidateへ置きません。

`CandidateArtifacts.load()` は以下を確定します。

- candidate ID
- selected variant
- decoder profile
- artifact contract
- artifact SHA-256 / size
- bundle SHA-256
- tokenizer kind/path
- graph I/O binding
- decoder config
- feature flags
- catalog ID/SHA

これらは `metadata.json` に逆流させません。

## 5. Revision boundary

config versionは4文書です。

```text
config/versions/config-000123/
├── reference.json
├── evaluation-schema.json
├── datasets-lock.json
└── runtime.json
```

fetch時にはlocalに次を生成します。

```text
.ci/hf/config/
├── current.json
├── resolved.json
└── revisions/
    ├── reference.json
    ├── evaluation-schema.json
    ├── datasets-lock.json
    └── runtime.json
```

`resolved.json` によって実行時の `config-NNNNNN` を明示します。revision bundle単体をversionlessに読む経路は現行contractにありません。

## 6. Execution boundary

`run-context.json` はrun開始前にexecution identityをfreezeするimmutable snapshotです。

含まれるもの:

- config/model/environment/provider/evaluation identity
- candidate primary artifact identity
- Git identity
- host identity
- ORT backend identity
- full revision snapshot
- resolved TOML snapshot
- generated candidate contract

PythonとRustはこのidentityを共有します。Rust用run-contextをPython側で生成しても、Rust runtimeがprovider readinessを実測するまでは「実行証明済み」とは扱いません。

## 7. Provider evidence

providerについて以下を区別します。

```text
compiled
registered
session_created
execution_proven
assignment_proven
```

`registered` は `execution_proven` を意味しません。CPU fallbackを許可したaccelerator runでは、inference成功だけでaccelerator利用を証明できません。

## 8. Promotion boundary

promotionでは次を再検証します。

- `run-context.json` schema/semantic contract
- `metrics.json` schema
- run ID一致
- candidate ID一致
- candidate bundle SHA一致
- acceptance passed
- 原則 `evaluation_id == "full"`

その後、Bucket candidateを再fetchしてbundle hashを再計算し、Model Repoへuploadします。promotion recordは `runs/<run-id>/promotion.json` に残します。
