# Hugging Face Buckets

## 役割

Hugging Face Bucketは開発・検証artifactを保存するための領域であり、Model Repoそのものではない。Model Repoは配布source、Bucketはconfig snapshot、candidate、run、benchmark、experiment/evidenceの保存先として使う。

現在のsource-controlled target例:

```text
Parakeet development bucket:
  gawohok7/jpapt-v2.2-dev-bucket

Parakeet model repository:
  gawohok7/jpapt-v2.2-dev

Bucket initializer E2E test bucket:
  gawohok7/ci-test
```

## Canonical tree

```text
/
├── README.md
├── bucket-manifest.json
├── config/
│   ├── README.md
│   ├── current.json
│   └── versions/
│       ├── README.md
│       └── config-NNNNNN/
│           ├── README.md
│           ├── reference.json
│           ├── evaluation-schema.json
│           ├── datasets-lock.json
│           └── runtime.json
├── candidates/
│   ├── README.md
│   └── <candidate-id>/
│       ├── README.md
│       ├── metadata.json
│       └── artifacts...
├── experiments/
│   ├── README.md
│   └── <experiment-id>/...
├── runs/
│   ├── README.md
│   └── <run-id>/
│       ├── run-context.json
│       ├── metrics.json
│       ├── samples.jsonl
│       └── promotion.json
└── benchmarks/
    ├── README.md
    └── <candidate-id>/
        └── <benchmark-name>/
            └── <run-id>.json
```

初期化直後は`README.md`群と`bucket-manifest.json`だけが存在し、`current.json`やversion/candidate/runはまだ作られない。

## NeMo validation evidence

candidate化前のNeMo→ONNX検証は正式candidate treeへ直接置かない。temporary experiment/evidence prefixを使う。

推奨例:

```text
experiments/
└── nemo-onnx/
    └── <validation-run-id>/
        ├── nemo-onnx-validation.json
        ├── nemo-reference-quality.json
        ├── ctc/
        │   ├── model.onnx
        │   └── model.onnx.data
        ├── tdt/
        │   ├── encoder.onnx
        │   ├── predictor.onnx
        │   └── joint.onnx
        ├── tokenizer/
        │   └── tokenizer.model
        ├── fixtures/
        │   └── ctc-reference.npz
        └── quality/
            ├── quality-comparison.json
            └── quality-samples.jsonl
```

このbundleがRust validation/quality gateを通過してからcentral allocatorでcandidate IDを発行する。

## Write-onceの考え方

candidateやrun identityを持つprefixは原則としてwrite-onceとして扱う。既存prefixを「修復」の名目で上書きしない。変更が必要なら新しいvalidation run / candidate / run IDを発行する。

Bucket initializerも同じ思想で、非空Bucketをreconcileしない。既存fileが1件でもあれば初期化を拒否する。

## `config/current.json`

`current.json`はversion directoryそのものではなく、現在選択するconfig versionへのpointerである。moving pointerをrun identityへ保存してはいけない。run開始時には具体的`config-NNNNNN`とdocument hashをsnapshotする。

## candidate publication

candidate publication前に最低限確認するもの:

- central allocatorで一意IDを取得したか
- candidate metadataがschemaに適合するか
- generated candidate contractがartifactを再hashしたか
- NeMo originの場合、pre-candidate validationがPASSしたか
- quality gateが要求されるrelease pathではNeMo↔ONNX regressionがthreshold内か
- sync planが意図しないdelete/overwriteを含まないか

## promotion record

promotionはartifact移動の代替ではなく、そのrun/candidateを採用したという記録である。

```text
runs/<run-id>/promotion.json
```

promotion時にもcandidate、config、evaluation、dataset revision identityを維持する。
