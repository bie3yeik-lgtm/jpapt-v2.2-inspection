# Hugging Face Buckets

## 1. Role of Buckets

Hugging Face Bucketはdevelopment/evaluation storageです。accepted release historyはHF Model Repoへpromotionし、Rust binary distributionはGitHub Releasesを使います。

Bucketに置くもの:

```text
config versions/current pointer
candidate artifacts
experiment namespace reservation
full run evidence
benchmark index
operational/reference/tmp directories
```

## 2. Current targets

```text
gawohok7/jpapt-v2.2-dev-bucket
  target: parakeet-tdt_ctc-0.6b-ja
  upstream: nvidia/parakeet-tdt_ctc-0.6b-ja
  profile_set: parakeet-tdt-ctc-v1
  model_repo: gawohok7/jpapt-v2.2-dev

gawohok7/tf-v1-onnx-dev-bucket
  target: kotoba-whisper-v1.0
  upstream: kotoba-tech/kotoba-whisper-v1.0
  profile_set: whisper-autoregressive-v1
  model_repo: gawohok7/tf-v1-onnx-dev
```

routing sourceは `config/hf-targets/*.toml` と `config/models/*.toml` / `config/asr-catalog.json` です。

## 3. Canonical logical tree

```text
hf://buckets/<namespace>/<bucket>/
├── README.md
├── config/
│   ├── current.json
│   └── versions/
│       └── config-NNNNNN/
│           ├── README.md
│           ├── reference.json
│           ├── evaluation-schema.json
│           ├── datasets-lock.json
│           └── runtime.json
├── candidates/
│   └── candidate-NNNNNN/
│       ├── README.md
│       ├── metadata.json
│       ├── <variant artifacts...>
│       └── tokenizer/...
├── experiments/
│   └── experiment-NNNNNN/
│       └── README.md
├── runs/
│   └── <run-id>/
│       ├── run-context.json
│       ├── samples.jsonl
│       ├── metrics.json
│       ├── run.parquet
│       └── promotion.json        # promotion後のみ
├── benchmarks/
│   └── candidate-NNNNNN/
│       └── <benchmark-name>/
│           └── <run-id>.json
├── reference/
├── scripts/
└── tmp/
```

`validate-hf-layout.yml` のmanual selected-target validationは、現在 `benchmarks`, `runs`, `candidates`, `experiments`, `reference`, `scripts`, `tmp` の各directoryが存在することを確認します。

## 4. Allocation policy

allocation catalog JSONはありません。

```text
collection     canonical prefix
candidates  -> candidate
experiments -> experiment
config      -> config
```

Rust `asr-hf` がcollectionからprefixを決定します。

sequenceはcanonical/historical layout双方に存在する6桁suffixの最大値 + 1です。migration前のIDを再利用しません。

## 5. Central allocator

`hf-central-allocator.yml` が中央採番serviceです。

input:

```text
request_id
hf_bucket
collection = candidates | experiments | config
metadata_json
```

同一Bucketについて:

```text
concurrency group = hf-central-sequence-<bucket>
cancel-in-progress = false
```

として直列化します。

allocation時にprefix rootへ `README.md` が先に作られる場合があります。これはnamespace reservationです。

## 6. Config storage

### `config/current.json`

active config versionを指すmutable pointerです。

### `config/versions/config-NNNNNN/`

immutable-by-policy snapshotです。

```text
reference.json           human-authored
 evaluation-schema.json   human-authored
 datasets-lock.json       human-authored
 runtime.json             generated
```

`runtime.json` はASR catalog fingerprint/profile setからRust publish toolingが生成します。

## 7. Candidate canonical layout

新規publish:

```text
candidates/candidate-NNNNNN/
```

candidate IDはprofile set/variant/workflow/providerをprefixへ含めません。

artifact semanticsは `metadata.json` + `config/asr-catalog.json` + actual artifact inspectionで決まります。

## 8. Historical candidate layout

既存Bucketにはhistorical layoutがあり得ます。

```text
candidates/ctc/candidate-NNNNNN/
candidates/tdt/candidate-NNNNNN/
```

これはread-only fallbackです。

ID省略readのpolicy:

```text
canonical candidateが存在する
  -> latest canonicalを選ぶ

canonical candidateが存在しない
  -> runtime variantを使ってhistorical candidateを解決
```

exact candidate ID指定でも同じresolverを使います。

## 9. HF CLI listing normalization

`hf buckets list <...>/candidates -R -q` の出力は実行条件によりcollection root付き/無しの双方があり得ます。

Rust resolverは次を同じrelative pathとして扱います。

```text
ctc/candidate-000001/metadata.json
candidates/ctc/candidate-000001/metadata.json
```

shell側でCLI出力形式を仮定してpathを切り刻まず、Rust resolverへ渡します。

## 10. Candidate publish safety

`hf-push-candidate.sh` はpublish前に:

- source candidate pathをcanonicalize
- sourceに `.candidate-id` が無いことを確認
- runtime contractをinspection/validate
- central allocatorからfresh ID取得
- `hf buckets sync --plan` 生成
- Rustでplanをparse
- `upload` 以外のactionを拒否

してからapplyします。

既存candidateを上書き/削除するsync planは受け入れません。

## 11. Candidate fetch

```bash
bash scripts/hf/hf-fetch-candidate.sh candidate-000124
```

local fetch先はfresh stagingを経由してmaterializeし、`.candidate-id` を作成します。

source candidateとfetched candidateを同じidentity表現にしない理由は、candidate IDがBucket allocationによって初めて確定するためです。

## 12. Experiments

```text
experiments/experiment-NNNNNN/
```

現在は中央AllocatorがREADME reservationを作る最小namespaceです。

1つのexperiment IDからcross-platform matrixの複数runが生成される場合があります。experiment IDとrun IDは別です。

## 13. Runs

runはexecution evidenceです。

```text
runs/<run-id>/
├── run-context.json
├── samples.jsonl
├── metrics.json
├── run.parquet
└── promotion.json   # optional
```

`run.parquet` はExperimentCapsuleV1です。

record types:

```text
manifest
sample
metric
artifact
diagnostic
```

large model/audioはParquet payloadへ複製せずexternal immutable referenceを使います。

## 14. Run upload

```bash
bash scripts/hf/hf-push-run.sh results/<run>
```

upload前に:

- JSON/JSONL schema
- run identity
- sample count
- ExperimentCapsuleV1

を検証します。

run uploadはremote cleanup目的の`--delete`を使用しません。

## 15. Benchmarks

```text
benchmarks/<candidate-id>/<benchmark-name>/<run-id>.json
```

full runを探索せずcandidate/provider/suite別metricsを比較するためのindexです。

例:

```text
linux-cpu-full
linux-cpu
windows-cpu
macos-cpu
macos-coreml
directml
coreml
parity
```

benchmark nameはsafe path componentである必要があります。

## 16. Promotion

promotionはBucket candidateを再fetchし、actual runtime contract/bundle SHAを検証してからModel Repoへuploadします。

Bucket側のrunには `promotion.json` を追加します。

Bucket candidateそのものをrelease historyの代替にしません。

## 17. Mutable vs immutable-by-policy

### Mutable

```text
config/current.json
README.md managed allocator status
```

### Immutable-by-policy

```text
config/versions/config-NNNNNN/
candidates/candidate-NNNNNN/
runs/<run-id>/
benchmarks/.../<run-id>.json
```

## 18. 実際の確認

selected targetのBucket構造はGitHub Actions `Validate HF Layout` をmanual dispatchすることで検証できます。

input:

```text
hf_target
runtime_variant (optional)
```

workflowはtargetをsource-controlled configから解決し、current config、4 revision documents、required directories、candidate resolverを実Bucket上で確認します。

詳細は [github-actions.md](./github-actions.md) と [workflows.md](./workflows.md) を参照してください。
