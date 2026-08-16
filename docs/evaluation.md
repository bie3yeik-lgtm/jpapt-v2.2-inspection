# Evaluation

## 1. 評価単位

1 evaluation runは、次のidentityの組み合わせです。

```text
model
candidate
runtime variant
provider
environment
evaluation suite
revision bundle
manifest
```

run開始時に `run-context.json` へfreezeし、終了後に `samples.jsonl` と `metrics.json` を生成します。

## 2. Evaluator capability

| evaluator | decoder | provider |
|---|---|---|
| Python ONNX | CTC / TDT / Whisper autoregressive | CPU / CUDA / DirectML / CoreML |
| Rust ONNX | CTC | CPU / CUDA / DirectML / CoreML |

Rust側でTDT/Whisperを選んだ場合はcapability validationでfailさせます。文書やCLI defaultで擬似対応しません。

## 3. Manifest

manifestはdataset全件のコピーではなく、deterministic selection requestです。

```json
{"dataset_id":"jsut-basic5000","count":12,"seed":"smoke-jsut-v1"}
```

`DatasetResolver` が `datasets-lock.json` のrepo/revisionと組み合わせ、実sampleをmaterializeします。

標準dataset例:

```text
id: jsut-basic5000
repo: japanese-asr/ja_asr.jsut_basic5000
```

## 4. Candidate load

評価前に必ず `CandidateArtifacts.load()` を通します。

検証対象:

- metadata schema
- profile-set / variant existence
- artifact role
- tokenizer kind/path
- artifact existence
- artifact size/hash
- ONNX graph I/O
- decoder-specific config
- non-ambiguous runtime contract

Python evaluatorとRust evaluatorでcandidate identityを別々に組み立てません。

## 5. Run context

`run-context.json` schema v2はrunのimmutable identityです。

run-context生成後にcandidate ID、revision bundle、provider、configを差し替えてはいけません。別条件で評価する場合は新しいrunを作ります。

Rust run-contextもPythonのstrict builderを使って生成できますが、runtime identityは `implementation=rust` として記録します。

## 6. Sample result

各sampleは `samples.jsonl` に1行ずつ書きます。

主な内容:

- dataset/sample identity
- audio hash / duration
- runtime/provider/decoder
- transcript / tokens
- CER/WER
- component timing
- memory
- parity
- provider evidence
- error records

失敗sampleも行を残し、aggregate時に `failed` として数えます。

## 7. Aggregate metrics

`metrics.json` は次を集約します。

- sample counts
- total audio duration
- CER/WER
- load/session/processing timing
- RTF
- per-sample latency distribution
- component timing
- RAM/device memory
- parity summary
- provider summary
- acceptance summary
- error summary

candidate identityの `artifact_sha256` はselected variantのbundle SHA-256です。単一ONNX fileのhashと混同しません。

## 8. Provider evidence

accelerator runでは、次を区別します。

```text
registered
execution_proven
fallback_detected
fallback_only
assigned_nodes
fallback_nodes
```

providerを登録できたことだけでaccelerator使用済みとは判定しません。

strict provider modeでCPU fallbackを禁止したrunでは、successful inferenceはexecution proofを強めます。ただしnode assignmentを直接観測していない場合、`assigned_nodes` は `null` のままです。

## 9. Acceptance

現行benchmark schemaは以下を持ちます。

```text
acceptance.passed
acceptance.quality_passed
acceptance.parity_passed
acceptance.provider_passed
acceptance.performance_passed
acceptance.failed_checks
acceptance.warnings
```

観測していないcheckをfalseにしません。非適用/未評価は `null` を使います。

## 10. Run publish

完全なrun directory:

```text
results/<run>/
├── run-context.json
├── samples.jsonl
└── metrics.json
```

publish:

```bash
scripts/hf/hf-push-run.sh results/<run>
```

remote:

```text
hf://buckets/${HF_BUCKET}/runs/<run-id>/
```

## 11. Benchmark index

比較用に `metrics.json` だけをindexできます。

```bash
scripts/hf/hf-push-benchmark.sh \
  results/<run>/metrics.json \
  cpu
```

remote:

```text
benchmarks/<candidate-id>/cpu/<run-id>.json
```

benchmark名は用途に応じて `cpu`, `cuda`, `directml`, `coreml`, `parity` 等を使えますが、path componentとして安全な名前に限定します。

## 12. Promotion

標準promotion条件:

- run-context valid
- metrics valid
- run ID一致
- candidate ID一致
- candidate bundle SHA一致
- `acceptance.passed == true`
- `evaluation_id == "full"`

実行:

```bash
scripts/hf/hf-promote-candidate.sh \
  parakeet-candidate-000124 \
  results/<run>
```

promotion scriptはBucket candidateを再downloadしてbundle hashを再計算します。その後Model Repoへuploadし、`promotion.json` をrunへ追加します。
