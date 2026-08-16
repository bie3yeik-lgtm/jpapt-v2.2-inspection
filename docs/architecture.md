# Architecture

## 1. 目的

このrepositoryは、日本語ASRモデルをONNXへ変換・検証し、Execution Providerごとの正確性・性能・provider利用実態を同一contractで比較し、accepted artifactをreleaseへ昇格させるための開発基盤です。

設計上の最重要原則は、**human-authored inputを最小化し、導出可能な値を二重入力しないこと**です。runtime-criticalな値はsource-controlled catalog/config、実artifact、revision lock、HF Bucket stateから導出し、一意に決められない場合はfailします。

## 2. Rust-first architecture

```text
Python-native / reference boundary
  ONNX/PyTorch/Transformers/NeMo tooling
  Hugging Face datasets acquisition/materialization
  public/reference E2E
          |
          | versioned file contracts
          v
Rust canonical core
  asr-contracts
  asr-hf
  asr-audio
  asr-runtime
  asr-metrics
  asr-eval
  asr-capsule
          |
          | thin shell + official hf/gh CLI
          v
HF Bucket / HF Model Repo / GitHub Actions / GitHub Releases
```

Python objectをproduction runtime contractとしてRustへ渡しません。境界はJSON/JSONL/Parquet等のversioned file contractです。

## 3. Source of truth

### Repository側

#### `config/asr-catalog.json`

- decoder profile
- artifact contract / required roles
- tokenizer kind
- runtime feature capability
- profile set / variant mapping
- default variant

#### `config/hf-targets/*.toml`

現行target inputは最小routing情報です。

```text
runtime.profile_set
storage.bucket
storage.model_repo
```

target IDはファイル名から、upstream/framework/model identityは `config/models/<target>.toml` から、runtime profile/decoderはASR catalogから導出します。

#### `config/models/*.toml`

model固有のruntime/execution semanticsとprovider compatibilityを保持します。HF storage path、candidate prefix、evaluation path等の共通routing policyは持ちません。

#### `config/providers/*.toml`

ORT provider/session条件。

#### `config/environments/*.toml`

現行environment:

```text
linux
windows
macos
```

#### `config/evaluation/*.toml`

smoke / parity / coreml-parity / full等の評価条件。

#### `config/evaluators/*.toml`

Python/Rust evaluator capabilityをsource-controlします。

#### `evaluation/schemas/*.schema.json`

persisted JSON/JSONL artifactsのstructure contract。

### HF Bucket側

```text
config/current.json
config/versions/config-NNNNNN/
candidates/candidate-NNNNNN/
experiments/experiment-NNNNNN/
runs/<run-id>/
benchmarks/<candidate-id>/<benchmark-name>/<run-id>.json
```

historical Bucketには `candidates/<variant>/candidate-NNNNNN/` が存在し得ますが、read-only fallbackです。新規writeはcanonical layoutへ収束します。

### HF Model Repo側

accepted candidateをpromotionしたrelease artifactを保持します。Bucketはdevelopment/evaluation storage、Model Repoはversioned release historyです。

### GitHub Releases

Rust `asr-eval` binaryは `rust-release.yml` によりLinux/Windows/macOS向けartifactとしてGitHub Releaseへpublishします。

## 4. Allocation architecture

allocation用JSON catalogはありません。

collectionからRustがcanonical prefixを導出します。

```text
candidates  -> candidate
experiments -> experiment
config      -> config
```

sequenceはcanonical/historical layout双方の6桁suffix最大値 + 1です。これによりmigration中もhistorical IDを再利用しません。

central allocatorは同一Bucket単位でGitHub Actions concurrencyにより直列化されます。

## 5. Data lifecycle

```text
upstream/public/source model
        |
        v
export / candidate finalize
        |
        v
local candidate
  metadata.json        human-authored minimal intent
  ONNX/tokenizer       actual artifacts
        |
        | Python-native ONNX inspection
        v
GeneratedCandidateContract
        |
        +-----------------------------+
        |                             |
        v                             v
Python evaluator                  Rust evaluator
CTC/TDT/Whisper                   CTC
        |                             |
        +-------------+---------------+
                      v
               execution evidence
               run-context.json
               samples.jsonl
               metrics.json
               run.parquet
                      |
                      v
              HF Bucket runs/<run-id>
                      |
               accepted full run
                      |
                      v
               HF Model Repo promotion
```

## 6. Candidate boundary

human-authored candidate contractは `metadata.json` のみです。

Parakeet例:

```text
candidate/
├── metadata.json
├── ctc/model.onnx
├── tdt/encoder.onnx
├── tdt/predictor.onnx
├── tdt/joint.onnx
└── tokenizer/vocabulary.json
```

`.candidate-id` はBucket fetch後のlocal identity markerであり、source candidateに事前配置しません。

ONNX inspection boundaryが確定する主なgenerated value:

- candidate ID
- selected variant
- runtime profile / decoder
- artifact contract
- artifact SHA-256 / size
- bundle SHA-256
- tokenizer kind/path
- graph I/O binding
- decoder-specific config
- feature flags
- catalog ID/SHA

これらをmetadataへ逆流させません。

## 7. Revision boundary

config versionは4文書です。

```text
config/versions/config-NNNNNN/
├── reference.json
├── evaluation-schema.json
├── datasets-lock.json
└── runtime.json
```

human-authoredは前3文書、`runtime.json` はRust publish toolingが生成します。

fetch後:

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

`resolved.json` がconcrete `config-NNNNNN` identityを固定します。

## 8. Dataset boundary

HF dataset acquisition/materializationはPython-native boundaryとして残します。

```text
datasets-lock.json
      |
      v
prepare-rust-manifest.py
      |
      v
ResolvedManifest
      |
      v
Rust evaluator
```

Rust runtimeがHF `datasets` objectへ直接依存する設計にはしません。

## 9. Execution boundary

`run-context.json` schema v2はrun開始前にexecution identityをfreezeするimmutable snapshotです。

含むもの:

- config/model/environment/provider/evaluation identity
- candidate artifact/bundle identity
- Git identity
- host/runtime identity
- ORT backend identity
- revision snapshot
- resolved TOML snapshot
- generated candidate contract
- experiment ID
- optimization/provider strictness

Rust evaluation pathでは `asr-contracts build-run-context` がcanonical builderです。

## 10. Result boundary

run directory:

```text
run-context.json
samples.jsonl
metrics.json
run.parquet
```

JSON/JSONLはinterchange/debug contract、ParquetはExperimentCapsuleV1のdurable analytical representationです。

Parquetへ大きなONNX/audio corpusを埋め込まず、artifact recordからimmutable URI/hash/sizeを参照します。

## 11. Provider evidence

provider状態を段階分離します。

```text
compiled
registered
session_created
execution_proven
assignment_proven
```

`registered == true` だけでaccelerator executionを証明したことにはしません。

non-CPU strict proofではCPU fallbackを禁止しますが、node assignmentを直接計測していなければ `assigned_nodes` は `null` のままです。

## 12. Evaluator capability

### Python

```text
CTC
TDT
Whisper autoregressive
```

### Rust

```text
CTC only
```

provider featureがCoreML/DirectML/CUDAに対応していても、TDT/Whisper decoderがRust実装済みという意味にはなりません。

## 13. GitHub Actions boundary

Actionsは以下を担当します。

- locked environment reproduction
- contract validation
- cross-platform build/test
- selected target/Bucket validation
- experiment allocation
- evaluation execution
- provider readiness proof
- public/reference E2E
- Rust binary release

runtime semanticsはworkflow YAMLへ複製しません。詳細は [github-actions.md](./github-actions.md)。

## 14. Promotion boundary

promotion前に最低限再検証します。

```text
run-context schema/semantic contract
metrics schema
run ID
candidate ID
candidate bundle SHA
acceptance.passed
evaluation_id == full
```

さらにBucket candidateを再fetchし、actual artifactからruntime contract/bundle identityを再検証してからModel Repoへuploadします。

## 15. Mutable / immutable separation

### Mutable

```text
config/current.json
Bucket root README managed allocator status
```

### Immutable-by-policy

```text
config/versions/config-NNNNNN/
candidates/candidate-NNNNNN/
runs/<run-id>/
benchmark documents keyed by run-id
```

mutable pointerをexecution evidenceの代わりに使いません。
