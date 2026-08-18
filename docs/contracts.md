# Contracts

## 1. Contract分類

現行repositoryでは入力・設定・execution artifactを次の3種類に分けます。

| 分類 | 例 | 人が直接編集するか |
|---|---|---|
| human-authored | candidate `metadata.json`, revision source 3文書 | はい。ただし最小限 |
| source-controlled | ASR catalog, model/provider/environment/evaluation/evaluator/HF target config | PRとしてのみ |
| generated | `runtime.json`, allocation response, `resolved.json`, generated candidate contract, `run-context.json`, `metrics.json`, `run.parquet`, `promotion.json`, candidate protocol receipt/ACK/lifecycle/timeline | いいえ |

最大の原則は **generated/derived valueをhuman-authored fileへコピーして正本を二重化しないこと**です。

## 2. Strictness

execution-critical contractでは以下を基本とします。

- unknown fieldを拒否する。
- current-versionで必須と定義されたexecution identityに `null` / empty stringを許さない。
- SHA-256は64 hexとして検証する。
- artifact pathがcandidate root外へescapeすることを拒否する。
- artifact存在、size、SHAをactual fileから再検証する。
- profile set / variant / decoder / artifact rolesをASR catalogとcross-checkする。
- config versionは `config-NNNNNN`。
- candidate IDは `candidate-NNNNNN`。
- experiment IDは `experiment-NNNNNN`。
- run-contextのcandidate/revision/config/catalog/provider identityをcross-checkする。

仕様上のcatalog defaultを選ぶことと、値がないから推測でdefaultを作ることは別です。前者だけを許可します。

後方互換contractでoptional fieldとして定義されているidentityを、同じschema versionのまま突然requiredへ変更してはいけません。特にcandidate protocol v1の `request_execution_id` はhistorical evidence互換のためoptionalです。新規Gateway/V2 evidenceでは生成しますが、v1 validatorはfield欠落を許容します。

## 3. Minimal HF target contract

`config/hf-targets/<target-id>.toml` はrouting最小入力です。

```toml
schema_version = 3

[runtime]
profile_set = "parakeet-tdt-ctc-v1"

[storage]
bucket = "gawohok7/jpapt-v2.2-dev-bucket"
model_repo = "gawohok7/jpapt-v2.2-dev"
```

ここへ以下を重複入力しません。

```text
target ID
upstream repo
framework
runtime variant
runtime profile
decoder
allocation prefix
candidate ID
```

導出元:

```text
target ID                <- filename
upstream/framework/model <- config/models/<target-id>.toml
profile/decoder/default  <- config/asr-catalog.json
allocation prefix        <- collection
candidate                <- explicit input or Bucket state
```

## 4. Candidate metadata

human-authored `metadata.json` はprofile setとartifact/tokenizer pathだけを表現します。

```json
{
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "artifacts": {"primary": "ctc/model.onnx"},
      "tokenizer": "tokenizer/vocabulary.json"
    },
    "tdt": {
      "artifacts": {
        "encoder": "tdt/encoder.onnx",
        "predictor": "tdt/predictor.onnx",
        "joint": "tdt/joint.onnx"
      },
      "tokenizer": "tokenizer/vocabulary.json"
    }
  }
}
```

metadataへ書かないもの:

```text
schema_version
candidate_id
catalog ID/SHA
bundle SHA
artifact SHA/size
runtime profile
decoder
artifact contract
input kind / graph I/O
blank/BOS/duration IDs
KV/state names/shapes/dtypes
provider support
evaluation/storage routing
```

## 5. ASR catalog

`config/asr-catalog.json` がruntime profile semanticsを一元管理します。

現行profile:

| profile | decoder | required artifact roles | tokenizer |
|---|---|---|---|
| `ctc-v1` | CTC | `primary` | vocabulary |
| `tdt-v1` | TDT | `encoder`, `predictor`, `joint` | vocabulary |
| `whisper-autoregressive-v1` | Whisper autoregressive | `encoder`, `decoder`; optional `decoder_with_past` | Transformers processor |

profile set:

```text
parakeet-tdt-ctc-v1
  default_variant = ctc
  ctc -> ctc-v1
  tdt -> tdt-v1

whisper-autoregressive-v1
  default_variant = whisper
  whisper -> whisper-autoregressive-v1
```

revision JSONやcandidate metadataへdecoder mappingを複製しません。

## 6. Revision bundle

human-authored source:

```text
reference.json
evaluation-schema.json
datasets-lock.json
```

publish時generated:

```text
runtime.json
```

versioned bundle:

```text
config/versions/config-NNNNNN/
├── reference.json
├── evaluation-schema.json
├── datasets-lock.json
└── runtime.json
```

`runtime.json` はASR catalog ID/SHAとprofile setをpinします。

fetch後は隣接する `resolved.json` がconcrete config versionを固定します。versionless revision bundleだけをexecution identityとして扱いません。

## 7. Allocation contract

allocation catalog JSONは存在しません。

```text
candidates  -> candidate
experiments -> experiment
config      -> config
```

allocation response schema v4は最小fieldです。

```json
{
  "schema_version": 4,
  "request_id": "...",
  "id": "candidate-000124",
  "bucket": "namespace/bucket",
  "collection": "candidates"
}
```

prefix key、catalog fingerprint、variant、provider等をresponseへ重複保存しません。

## 8. Candidate location contract

new write:

```text
candidates/candidate-NNNNNN/
```

historical read-only fallback:

```text
candidates/<variant>/candidate-NNNNNN/
```

canonical candidateが1つでも存在する場合、ID省略readはcanonicalを優先します。historical pathはmigration inputであり、新規publish targetではありません。

## 9. Generated candidate contract

Python-native ONNX inspection boundaryがactual filesから生成します。

含まれる主なidentity:

- candidate root / candidate ID
- profile set / variant / profile / decoder
- artifact contract
- catalog ID/SHA
- bundle SHA
- roleごとのpath/SHA/size
- tokenizer kind/path
- features
- graph I/O binding
- decoder config

Rust evaluator/policyはこのfile contractを独立して検証・消費します。

## 10. Resolved manifest

HF dataset acquisitionはPython-nativeですが、Rust runtimeへ渡すのはPython objectではなくmaterialized/resolved manifestです。

execution snapshot時にはdataset revision/hash/manifest identityが確定している必要があります。

## 11. Run context

`run-context.json` schema v2はimmutable execution snapshotです。

必須identityの代表:

- target/model
- candidate ID / bundle / selected artifact
- runtime variant/profile/decoder
- Git repository / commit / ref / dirty
- host OS / arch / hostname
- runtime implementation / ORT / provider
- config version / revision bundle SHA
- dataset/manifest
- resolved config snapshot
- generated candidate contract
- experiment ID

外部から読んだrun-contextもJSON Schemaだけでなくtyped semantic cross-checkを行います。

## 12. Candidate protocol identity

外部candidate orchestrationでは3種類のidentityを分離します。

```text
request_id            caller-visible logical correlation
request_execution_id  one Gateway/V2 execution
receipt_sha256         canonical completion receipt content
```

生成規則:

```text
Gateway        gw-<github.run_id>-<github.run_attempt>
Direct V2      eval-<github.run_id>-<github.run_attempt>
```

`repository_dispatch` callerが送った `request_execution_id` をGatewayのtrusted identityとして採用しません。Gateway normalizationが自身の `gw-*` identityへ置換し、その値をV2へforwardします。V2 direct invocationではinputが空の場合のみ `eval-*` を生成します。

新規evidenceではexecution identityを次へ伝播します。

```text
planned / dispatched / running lifecycle
rejection
completion receipt
ACK
completed / acknowledged lifecycle
execution-scoped timeline
```

`CandidateRequestTimelineV1.request_execution_id` はqueryが特定executionへ絞られた場合だけtop-levelへ出力します。fieldが存在するtimelineでは、全 `events[].snapshot.request_execution_id` が同じ値でなければbuilder/validatorが拒否します。

persistent lifecycleはrequest aggregateとexecution partitionを分けます。

```text
requests/<request-key>/...
requests/<request-key>/executions/<execution-key>/...
```

`request_execution_id` の詳細は `docs/request-execution-identity.md`、delivery/state semanticsは `docs/candidate-completion-protocol.md` を正規説明とします。

## 13. Sample / metrics nullable policy

`run-context` identityはnull禁止ですが、観測結果には `null` が必要です。

例:

```text
node assignment未計測 -> assigned_nodes: null
parity非対象 -> parity numeric field: null
device memory未取得 -> peak_device_memory_mb: null
```

未観測を0/falseへ捏造しません。

## 14. ExperimentCapsuleV1

`run.parquet` はgenerated durable analytical contractです。

record kind:

```text
manifest
sample
metric
artifact
diagnostic
```

JSON/JSONL execution evidenceとidentityを一致させ、run upload前に検証します。

large artifactはParquetへ複製せず、immutable external URI/hash/sizeを参照します。

## 15. Promotion contract

promotion前に再検証します。

```text
run-context valid
metrics valid
run ID一致
candidate ID一致
candidate bundle SHA一致
acceptance.passed == true
原則 evaluation_id == full
```

さらにBucket candidateを再fetchしてactual bundle/runtime contractを検証します。

## 16. Rust / Python boundary

PythonはCTC/TDT/Whisper runtimeおよびML/tooling/reference pathを持ちます。Rust evaluatorは現時点でCTCのみです。

境界はversioned file contractです。

```text
Python ONNX inspection -> GeneratedCandidateContract -> Rust
Python HF datasets -> ResolvedManifest -> Rust
Rust capsule -> run.parquet -> Python compatibility reader
```

capability差をmetadataやfallback codeで隠しません。
