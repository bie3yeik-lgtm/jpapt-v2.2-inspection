# Workflows

## 1. 基本方針

GitHub Actionsは、source-controlled contractとHF Bucket上のimmutable-by-policy artifactを接続するexecution layerです。

workflowにruntime semanticsを再定義しません。workflowは次のsource of truthを呼び出します。

```text
config/asr-catalog.json
config/hf-targets/*.toml
config/models/*.toml
config/providers/*.toml
config/environments/*.toml
config/evaluation/*.toml
evaluation/schemas/*.schema.json
```

## 2. Core CI

### Python Unit

目的:

- locked uv environment
- pinned ONNX Runtime
- Python unit tests
- strict contract parser
- candidate/revision/runtime validation

標準環境:

```bash
uv lock --check
uv sync --locked --extra datasets --extra onnx --extra dev
uv run python -m pytest -q python/tests/unit
```

### Validate HF Layout

目的:

- source-controlled catalogs
- HF target routing
- JSON/schema contracts
- HF shell scripts syntax
- optimizer canary
- dependency pins

### Rust CI

matrix:

```text
Linux   -> CPU
Windows -> DirectML
macOS   -> CoreML
```

各matrixでlockfile/check/clippy/testsを実施します。

CI成功はreal-model accelerator E2Eと同義ではありません。real-model E2Eは別workflowで扱います。

## 3. HF target resolution

例:

```text
parakeet-tdt_ctc-0.6b-ja
  -> nvidia/parakeet-tdt_ctc-0.6b-ja
  -> parakeet-tdt-ctc-v1
  -> gawohok7/jpapt-v2.2-dev-bucket
  -> gawohok7/jpapt-v2.2-dev

kotoba-whisper-v1.0
  -> kotoba-tech/kotoba-whisper-v1.0
  -> whisper-autoregressive-v1
  -> gawohok7/tf-v1-onnx-dev-bucket
  -> gawohok7/tf-v1-onnx-dev
```

runtimeで手入力したBucket/Model Repoを正本にせず、target configから解決します。

## 4. Config version publish

source directoryには3つのhuman-authored documentを用意します。

```text
reference.json
evaluation-schema.json
datasets-lock.json
```

`runtime.json` はpublish scriptが生成します。

```bash
export HF_TOKEN=...
export HF_TARGET_ID=parakeet-tdt_ctc-0.6b-ja
export HF_BUCKET=gawohok7/jpapt-v2.2-dev-bucket

scripts/hf/hf-push-config-version.sh ./revision-source
```

内部処理:

1. human-authored 3文書を検証
2. decoder宣言重複を拒否
3. target/profile setを解決
4. `runtime.json` をcatalog fingerprintから生成
5. revision bundle SHAを計算
6. 中央Allocatorへconfig IDを要求
7. `config/versions/config-NNNNNN/` へpublish
8. `config/current.json` を更新

## 5. Config fetch

```bash
scripts/hf/hf-fetch-revisions.sh
```

生成local layout:

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

`HF_CONFIG_VERSION` を指定した場合はcurrent pointerではなく明示versionを選び、`resolved.json.selection_source` が `override` になります。

現行strict loaderでは `runtime.json` と `resolved.json` が必須です。script内にlegacy説明が残っていても、execution contractとしてlegacy 3-file configを正当化しません。

## 6. Candidate publish

candidate source:

```text
candidate/
├── metadata.json
├── *.onnx / subgraphs
└── tokenizer/...
```

publish:

```bash
export HF_TOKEN=...
export HF_BUCKET=gawohok7/jpapt-v2.2-dev-bucket

scripts/hf/hf-push-candidate.sh ./candidate
```

内部処理:

1. `metadata.json` 検証
2. profile setをcatalogで解決
3. 全variantをload/inspect
4. runtime contract validation
5. allocation catalogからprefix key解決
6. 中央Allocatorへcandidate ID要求
7. `hf buckets sync --plan`
8. fresh `upload` 以外のoperationを拒否
9. exact planをapply

source candidateに `.candidate-id` が既に存在する場合はrepublishを拒否します。

## 7. Candidate fetch

fetch後local materializationでは `.candidate-id` を作り、Bucket identityをcandidate loaderへ渡します。

fetch先を再利用して古いfileを混在させず、fresh stagingから置換する運用を使用します。

## 8. Python evaluation

標準フロー:

```text
resolve target/config
      ↓
fetch revisions
      ↓
fetch candidate
      ↓
resolve dataset manifest
      ↓
strict run-context build
      ↓
Python evaluator
      ↓
run-context.json + samples.jsonl + metrics.json
```

Python evaluatorはCTC/TDT/Whisper autoregressiveを扱います。

## 9. Rust evaluation

Rust evaluatorへ直接human metadataを渡しません。

```text
candidate directory
      ↓ Python inspection
GeneratedCandidateContract
      ↓
strict RunContext
      ↓
Rust CTC evaluator
```

代表的なCI script:

```bash
python scripts/ci/resolve-candidate-artifacts.py \
  --candidate-dir .ci/hf/candidate \
  --runtime-variant ctc \
  --contract-out .ci/candidate-contract.json

cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  build-run-context \
  --repository-root . \
  --model parakeet-tdt_ctc-0.6b-ja \
  --provider cpu \
  --evaluation full \
  --environment linux \
  --revisions .ci/hf/config/revisions \
  --candidate-contract .ci/candidate-contract.json \
  --runtime-variant ctc \
  --output .ci/run-context.json
```

Rust evaluatorのdecoder capabilityはCTCのみです。

## 10. Strict provider diagnostics

Rust run-context生成では次をoverrideできます。

```text
--strict-provider
--optimization-level configured|disable|basic|extended|all
```

`--strict-provider` はnon-CPU providerでCPU fallbackを無効化するproof run用です。

DirectMLではsession設定が次を満たさない場合runtime guardでfailします。

```text
sequential execution
memory pattern disabled
```

## 11. Run upload

```bash
scripts/hf/hf-push-run.sh results/<run>
```

必須:

```text
run-context.json
metrics.json
samples.jsonl
```

upload前にrun ID一致とschema validationを行います。

## 12. Benchmark upload

```bash
scripts/hf/hf-push-benchmark.sh \
  results/<run>/metrics.json \
  cpu
```

remote:

```text
benchmarks/<candidate-id>/cpu/<run-id>.json
```

## 13. Promotion

```bash
scripts/hf/hf-promote-candidate.sh \
  candidate-000124 \
  results/<run>
```

標準条件:

```text
acceptance.passed == true
evaluation_id == full
candidate ID一致
candidate bundle SHA一致
run ID一致
```

promotion scriptはcandidateをBucketから再fetchしてbundle hashを再計算し、release stagingへ `run-context.json`, `metrics.json`, `promotion.json` を加えてHF Model Repoへuploadします。

## 14. 中央Allocator

ID collection:

```text
candidates
experiments
config
```

prefixはcollectionからRustが決定します。workflowはprefix keyを入力せず、candidate IDも省略時は対象Bucketから自動解決します。

採番はcollection内に存在する全prefixの6桁suffixを走査し、最大値+1を採用します。ID suffixを人が選びません。

Allocatorは採番時に対象prefixへ `README.md` を作成し、Bucket root `README.md` のmanaged blockも更新します。

## 15. Real-model E2E

実モデルE2Eの標準fixture:

```text
DirectML / Whisper:
  kotoba-tech/kotoba-whisper-v1.0

CTC:
  nvidia/parakeet-tdt_ctc-0.6b-ja

Dataset:
  japanese-asr/ja_asr.jsut_basic5000
```

DirectMLはWindows runnerで実行します。HF JobsはLinuxなのでDirectML execution proofには使用しません。

## 16. 変更時の確認順序

contractまたはworkflowを変更した場合:

```text
1. source-controlled schema/catalog
2. Python strict parser/unit
3. HF layout validation
4. Rust CI
5. real-model E2E（必要な変更のみ）
6. candidate/run/promotion dry run
```

CIを通すためにlegacy parserやnullable compatibilityを戻すことはしません。fixture/workflowを現行contractへ移行します。
