# Hugging Face Bucket Layout

Bucketはframework/providerごとにtreeを分岐しません。candidate/config/run/benchmarkというライフサイクル単位で整理します。

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
├── experiments/<experiment-id>/README.md
├── candidates/<candidate-id>/
│   ├── README.md
│   ├── metadata.json
│   └── <artifacts/tokenizer/config assets>
├── reference/
│   ├── manifests/
│   ├── outputs/
│   ├── tensors/
│   └── metadata/
├── runs/<run-id>/
│   ├── run-context.json
│   ├── samples.jsonl
│   ├── metrics.json
│   └── promotion.json
├── benchmarks/<candidate-id>/<environment-provider>/<run-id>.json
├── scripts/
└── tmp/
```

## Config version

`runtime.json` を含む4文書がcanonical bundleです。`config/current.json` は現在versionへのpointerで、過去version自体はimmutableです。

## Candidate

candidate IDはallocatorがdirectory名として決定します。`metadata.json` はID/hash/bindingを持たずminimal inputのまま保存します。

## Run

runは実行時routing・candidate provenance・revision・host/providerを `run-context.json` にsnapshotします。過去runを現在のRepository Variableから再推定しません。

## 禁止するtree軸

`nemo/`, `transformers/`, `ctc/`, `tdt/`, `coreml/` 等をBucket rootの別体系として増やしません。差分はprofile/variant/provider metadataで表現します。
