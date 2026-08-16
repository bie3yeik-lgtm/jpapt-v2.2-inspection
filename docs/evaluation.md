# Evaluation

## 1. 評価単位

1 evaluation runは次のidentityの組み合わせです。

```text
model / HF target
candidate
runtime variant / runtime profile / decoder
provider
environment
evaluation suite
config version / revision bundle
dataset manifest
experiment ID
optimization/provider strictness
```

run開始時に `run-context.json` へfreezeし、終了時にper-sample/aggregate/capsuleを生成します。

## 2. Evaluator capability

| evaluator | decoder | provider |
|---|---|---|
| Python ONNX | CTC / TDT / Whisper autoregressive | CPU / CUDA / DirectML / CoreML |
| Rust ONNX | CTC | CPU / CUDA / DirectML / CoreML |

Rust側でTDT/Whisperを選ぶとcapability validationでfailします。provider feature対応とdecoder対応は独立です。

## 3. Evaluation suites

source-controlled suiteは `config/evaluation/*.toml` にあります。workflow inputで現行使用される代表値:

```text
smoke
parity
coreml-parity
full
```

suiteごとのsample selection、acceptance threshold、parity/performance条件はworkflowへ直接埋め込まずconfigから解決します。

## 4. Dataset / manifest boundary

manifestはdataset全体のcopyではなくdeterministic selection requestです。

```json
{"dataset_id":"jsut-basic5000","count":12,"seed":"smoke-jsut-v1"}
```

`datasets-lock.json` がrepo/revision/hash/manifest identityをpinし、Python `datasets` boundaryが実audioをmaterializeします。

Rust pathでは `scripts/ci/prepare-rust-manifest.py` がresolved manifestを生成し、その後Rust runtimeは通常のfile I/Oでmaterialized audioを読みます。

標準dataset:

```text
japanese-asr/ja_asr.jsut_basic5000
```

## 5. Candidate selection

workflow inputの `candidate_id` はoptionalです。

明示された場合:

```text
candidate-NNNNNN formatを検証
```

空の場合:

1. targetからBucket/runtime variantを解決
2. Bucket candidate listing取得
3. Rust `resolve-candidate-location`
4. canonical latest candidateを優先
5. canonicalが無いhistorical Bucketだけvariant配下へfallback

new candidate writeは常にcanonical pathです。

## 6. Candidate load / generated contract

評価前にactual artifactをinspectionします。

検証/生成対象:

- metadata profile set/variant
- artifact role/path
- tokenizer kind/path
- artifact existence
- artifact size/hash
- bundle hash
- ONNX graph I/O
- decoder-specific runtime config
- catalog/profile/decoder identity
- feature flags

Python-native ONNX toolingの結果をgenerated candidate contractへ書き出し、Rust evaluator/policyも同じcontractを消費します。

## 7. Run context

`run-context.json` schema v2はrunのimmutable identityです。

Rust evaluation pathでは:

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  build-run-context ...
```

で構築します。

run-context生成後にcandidate、revision、provider、suiteを差し替えてはいけません。条件が違えば新しいrunです。

## 8. Per-sample result

各sampleは `samples.jsonl` に1行ずつ保存します。

主な内容:

- dataset/sample identity
- audio SHA/duration
- provider/runtime/decoder
- transcript/tokens
- CER/WER
- timing
- memory
- parity
- provider evidence
- structured errors

失敗sampleもrecordを残し、aggregateでfailed countへ反映します。

## 9. Aggregate metrics

`metrics.json` は代表的に以下を集約します。

- attempted/succeeded/failed sample count
- audio duration
- CER/WER
- load/session/processing timing
- RTF
- latency distribution
- component timing
- RAM/device memory
- parity summary
- provider summary
- acceptance
- error summary

candidateのbundle identityと単一ONNX file hashを混同しません。

## 10. ExperimentCapsuleV1 / `run.parquet`

現行runはJSON/JSONLに加えて `run.parquet` を持ちます。

```text
results/<run>/
├── run-context.json
├── samples.jsonl
├── metrics.json
└── run.parquet
```

Parquetはcross-run analysis向けdurable representationです。

record kind:

```text
manifest
sample
metric
artifact
diagnostic
```

大きなmodel/audio/traceをpayloadへ複製せず、artifact recordからimmutable URI、SHA-256、sizeを参照します。

Rust `asr-capsule` がcanonical write/validationを担い、`capsule-interop.yml` でRust生成fileをPython readerでも読みます。

## 11. Provider evidence

accelerator評価では次を分離します。

```text
registered
session_created
execution_proven
fallback_detected
fallback_only
assigned_nodes
fallback_nodes
```

providerを登録できたことだけでaccelerator使用済みとは判定しません。

strict provider modeではnon-CPU providerのCPU fallbackを禁止し、execution proofを強めます。それでもnode assignmentを直接観測していない場合は `assigned_nodes: null` です。

## 12. Acceptance

benchmark schemaの代表field:

```text
acceptance.passed
acceptance.quality_passed
acceptance.parity_passed
acceptance.provider_passed
acceptance.performance_passed
acceptance.failed_checks
acceptance.warnings
```

非適用/未観測をfalseに偽装せず `null` を使います。

## 13. Run ID / experiment ID

experiment ID:

```text
experiment-NNNNNN
```

中央Allocatorが評価開始前に採番します。

run IDはexecution identityから生成されるrun固有IDであり、experiment IDとは別です。1 experiment namespaceから複数platform runが生まれるworkflowがあります。

## 14. Result validation

Rust validator:

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  validate-run results/<run>
```

run-context / samples / metrics / capsule間のidentityと件数をcross-checkします。

## 15. Run publish

```bash
bash scripts/hf/hf-push-run.sh results/<run>
```

remote:

```text
hf://buckets/${HF_BUCKET}/runs/<run-id>/
```

upload wrapperはremote objectを削除する `--delete` 前提にしません。

`cpu-full-eval.yml` と `cross-platform-parity.yml` はrunをHF Bucketへuploadします。現行 `rust-eval.yml` はGitHub artifact uploadまでで、HF run publishは実施しません。

## 16. Benchmark index

```bash
bash scripts/hf/hf-push-benchmark.sh \
  results/<run>/metrics.json \
  <benchmark-name>
```

remote:

```text
benchmarks/<candidate-id>/<benchmark-name>/<run-id>.json
```

benchmarkは比較用lightweight indexであり、full run/capsuleの代替ではありません。

## 17. GitHub Actionsによる評価

### CPU Full Evaluation

- Python evaluator
- Linux CPU
- `full`
- timeout 360分
- HF run upload
- benchmark publish
- GitHub lightweight artifact 7日

### Cross Platform ONNX Parity

Python evaluator matrix:

```text
Linux CPU
Windows CPU
macOS CPU
macOS CoreML
```

suite:

```text
smoke | parity | coreml-parity
```

各runをHFへpublishし、成功時benchmarkを作ります。

### Rust Cross Platform Evaluation

Rust CTC matrix:

```text
Linux CPU
Windows CPU
Windows DirectML
macOS CPU
macOS CoreML
```

input:

```text
smoke | parity | coreml-parity | full
strict_provider
optimization_level
```

詳細は [github-actions.md](./github-actions.md)。

## 18. Promotion

標準promotion条件:

```text
run-context valid
metrics valid
run ID一致
candidate ID一致
candidate bundle SHA一致
acceptance.passed == true
evaluation_id == full
```

```bash
bash scripts/hf/hf-promote-candidate.sh \
  candidate-000124 \
  results/<run>
```

promotion時はBucket candidateを再fetchしてactual artifactからbundle/runtime contractを再検証します。その後Model Repoへuploadし、`promotion.json` をrunへ記録します。

## 19. どの評価を使うか

| 目的 | 推奨 |
|---|---|
| 軽いcontract/runtime smoke | Rust/Python `smoke` |
| OS間のPython ONNX比較 | Cross Platform ONNX Parity |
| CoreML numerical parity | `coreml-parity` |
| release gate用の標準品質評価 | CPU Full Evaluation |
| Rust CTC provider別runtime | Rust Cross Platform Evaluation |
| accelerator fallbackなしproof | Provider Strict Probes |
| production candidateに依存しないreference E2E | Public Model E2E |
