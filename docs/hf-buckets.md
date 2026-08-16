# Hugging Face Buckets

## 1. 実際に使うdevelopment Bucket

source-controlled target定義では、少なくとも次の2系統を使います。

```text
gawohok7/jpapt-v2.2-dev-bucket
└── target: parakeet-tdt_ctc-0.6b-ja
    upstream: nvidia/parakeet-tdt_ctc-0.6b-ja
    profile_set: parakeet-tdt-ctc-v1
    model_repo: gawohok7/jpapt-v2.2-dev

gawohok7/tf-v1-onnx-dev-bucket
└── target: kotoba-whisper-v1.0
    upstream: kotoba-tech/kotoba-whisper-v1.0
    profile_set: whisper-autoregressive-v1
    model_repo: gawohok7/tf-v1-onnx-dev
```

両Bucketは同じlogical layoutを使います。

## 2. 標準Bucket tree

実装されているscript群から見た標準treeは次です。

```text
hf://buckets/<namespace>/<bucket>/
├── README.md
├── config/
│   ├── current.json
│   └── versions/
│       ├── config-000001/
│       │   ├── README.md
│       │   ├── reference.json
│       │   ├── evaluation-schema.json
│       │   ├── datasets-lock.json
│       │   └── runtime.json
│       └── config-000002/
│           ├── README.md
│           ├── reference.json
│           ├── evaluation-schema.json
│           ├── datasets-lock.json
│           └── runtime.json
├── candidates/
│   ├── parakeet-candidate-000003/
│   │   ├── README.md
│   │   ├── metadata.json
│   │   ├── ctc/
│   │   │   └── model.onnx
│   │   ├── tdt/
│   │   │   ├── encoder.onnx
│   │   │   ├── predictor.onnx
│   │   │   └── joint.onnx
│   │   └── tokenizer/
│   │       └── vocabulary.json
│   └── whisper-candidate-000004/
│       ├── README.md
│       ├── metadata.json
│       ├── encoder.onnx
│       ├── decoder.onnx
│       ├── decoder_with_past.onnx
│       └── tokenizer/
│           ├── tokenizer_config.json
│           ├── preprocessor_config.json
│           └── ...
├── experiments/
│   ├── cpu-full-eval-000005/
│   │   └── README.md
│   ├── cross-platform-parity-000006/
│   │   └── README.md
│   └── rust-eval-000007/
│       └── README.md
├── runs/
│   └── 20260816T120000Z-parakeet-tdt-ctc-0.6b-ja-linux-cpu-full-12345678-abcd1234/
│       ├── run-context.json
│       ├── metrics.json
│       ├── samples.jsonl
│       ├── run.parquet
│       └── promotion.json        # promotion後のみ
└── benchmarks/
    └── parakeet-candidate-000003/
        ├── cpu/
        │   └── <run-id>.json
        ├── cuda/
        │   └── <run-id>.json
        ├── directml/
        │   └── <run-id>.json
        └── coreml/
            └── <run-id>.json
```

注意: `README.md` は中央AllocatorがID予約時に先に作ることがあります。candidate publishはその後、同じcandidate prefixへartifactを追加します。

## 3. Parakeet Bucketの具体例

```text
hf://buckets/gawohok7/jpapt-v2.2-dev-bucket/
├── README.md
├── config/
│   ├── current.json
│   └── versions/
│       └── config-000123/
│           ├── README.md
│           ├── reference.json
│           ├── evaluation-schema.json
│           ├── datasets-lock.json
│           └── runtime.json
├── candidates/
│   └── parakeet-candidate-000124/
│       ├── README.md
│       ├── metadata.json
│       ├── ctc/model.onnx
│       ├── tdt/encoder.onnx
│       ├── tdt/predictor.onnx
│       ├── tdt/joint.onnx
│       └── tokenizer/vocabulary.json
├── experiments/
│   └── rust-eval-000125/README.md
├── runs/
│   └── <run-id>/
│       ├── run-context.json
│       ├── metrics.json
│       ├── samples.jsonl
│       ├── run.parquet
│       └── promotion.json
└── benchmarks/
    └── parakeet-candidate-000124/
        └── cpu/<run-id>.json
```

## 4. Whisper Bucketの具体例

```text
hf://buckets/gawohok7/tf-v1-onnx-dev-bucket/
├── README.md
├── config/
│   ├── current.json
│   └── versions/
│       └── config-000041/
│           ├── README.md
│           ├── reference.json
│           ├── evaluation-schema.json
│           ├── datasets-lock.json
│           └── runtime.json
├── candidates/
│   └── whisper-candidate-000042/
│       ├── README.md
│       ├── metadata.json
│       ├── encoder.onnx
│       ├── decoder.onnx
│       ├── decoder_with_past.onnx
│       └── tokenizer/...
├── runs/
│   └── <run-id>/
│       ├── run-context.json
│       ├── metrics.json
│       ├── samples.jsonl
│       └── run.parquet
└── benchmarks/
    └── whisper-candidate-000042/
        └── directml/<run-id>.json
```

## 5. `config/`

### `config/current.json`

現在のactive config versionを指すmutable pointerです。

### `config/versions/config-NNNNNN/`

各versionはimmutable snapshotとして扱います。内容は4文書です。

```text
reference.json
evaluation-schema.json
datasets-lock.json
runtime.json
```

中央Allocatorが先に `README.md` を作成し、`hf-push-config-version.sh` が4文書をpublishします。

## 6. `candidates/`

candidate IDは中央Allocatorがcanonical/historical layout双方の最大6桁suffixを見て `candidate-NNNNNN` を自動採番します。prefix設定JSONは不要です。candidate IDを省略したreadではcanonical `candidates/candidate-NNNNNN` の最新値を優先し、canonicalが存在しない既存Bucketに限って `<variant>/candidate-NNNNNN` をread-only fallbackとして解決します。

現在のprefix:

```text
candidate.parakeet-tdt-ctc-v1  -> parakeet-candidate
candidate.whisper-autoregressive-v1 -> whisper-candidate
```

publish時は `hf buckets sync --plan` の結果を確認し、fresh upload以外のoperationが必要なら拒否します。candidate IDを再利用して既存artifactを上書きする運用はしません。

## 7. `experiments/`

experiment IDも中央Allocator管理です。

```text
experiment.cpu_full              -> cpu-full-eval
experiment.cross_platform_parity -> cross-platform-parity
experiment.rust_eval             -> rust-eval
```

現状、AllocatorのREADMEがnamespace reservationの最小artifactです。workflowが追加artifactを置く場合も同じexperiment ID配下を使います。

## 8. `runs/`

runは最低限次の4ファイルを持ちます。

```text
run-context.json
metrics.json
samples.jsonl
run.parquet
```

`run.parquet` は ExperimentCapsuleV1 のdurable analytical representationです。現在は同一flat schema上に `manifest` / `sample` / `metric` / `artifact` / `diagnostic` recordを保持します。

- `manifest`: run-contextとbenchmark provenance
- `sample`: per-sample ASR結果
- `metric`: cross-run集計向けnumeric metric
- `artifact`: 小さなembedded artifactまたはHF Bucket等のexternal immutable artifact参照
- `diagnostic`: provider fallback、parity、frontend/runtime等の小さな構造化診断

大きなONNX model、external data、audio corpus、大規模traceはParquet payloadへ複製せず、`artifact` recordからimmutable URI・SHA-256・sizeを参照します。

`hf-push-run.sh` はJSON/JSONL schemaに加えて `run.parquet` のExperimentCapsuleV1整合性、run ID、sample数を検証してから `runs/<run-id>/` へdirectory syncします。run upload wrapperでは `--delete` を使用しません。

promotion成功後は同じrunへ `promotion.json` を追加します。

## 9. `benchmarks/`

軽量なmetrics indexです。

```text
benchmarks/<candidate-id>/<benchmark-name>/<run-id>.json
```

格納される内容はrunの `metrics.json` と同じbenchmark documentです。run本体を探索せずcandidate/provider単位で比較したい場合に使います。

## 10. BucketとModel Repoの責務

Bucket:

- development artifact
- mutable current pointer
- immutable-by-policy config/candidate IDs
- raw run history + ExperimentCapsuleV1
- benchmark index

Model Repo:

- accepted release artifact
- versioned repository history
- downstream consumer向け成果物

promotionではBucket candidateを再fetchしてbundle SHAを再検証した後、Model Repoへuploadします。
