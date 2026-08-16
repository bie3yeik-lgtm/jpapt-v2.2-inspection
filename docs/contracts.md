# Contracts

## 1. Contract分類

このprojectではJSONを3種類に分けます。

| 分類 | 例 | 人が編集するか |
|---|---|---|
| human-authored | candidate `metadata.json`, revision 3文書 | はい。ただし最小限 |
| source-controlled | `config/asr-catalog.json`, `config/hf-allocation-catalog.json` | repository変更としてのみ |
| generated | `runtime.json`, `current.json`, `resolved.json`, generated candidate contract, `run-context.json`, `metrics.json`, `promotion.json` | いいえ |

生成値をhuman-authored JSONへコピーして正本を二重化しないことが最重要です。

## 2. Strictness

execution-critical JSONでは以下を基本方針とします。

- unknown fieldを拒否する
- execution identityに `null` を許さない
- empty stringをidentityとして扱わない
- SHA-256は64 hexで検証する
- candidate artifactは存在・size・SHAを再検証する
- candidate-relative pathがroot外へescapeすることを拒否する
- profile set / variant / decoder / artifact contractはcatalogと一致させる
- run-contextのcandidate ID / catalog / profile set / artifact identityをcross-checkする
- config versionは `config-NNNNNN` のみ

「値が無い場合に適当なdefaultを入れる」ことと、「仕様で定義されたdefault variantをcatalogから選ぶ」ことは別です。前者は推測であり禁止、後者はsource of truthからの決定です。

## 3. Candidate metadata

human-authored `metadata.json` は以下だけを表現します。

```json
{
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "artifacts": {
        "primary": "ctc/model.onnx"
      },
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

禁止される代表例:

```text
schema_version
candidate_id
catalog
bundle_sha256
artifact sha256 / size
profile
artifact_contract
decoder
input_kind
I/O binding
blank_id / bos_id / durations
KV cache names
state shapes / dtypes
features
```

これらはgenerated candidate contract側の責務です。

## 4. Runtime catalog

`config/asr-catalog.json` がdecoder semanticsを一元管理します。

現在のprofile:

| profile | decoder | artifact roles | tokenizer |
|---|---|---|---|
| `ctc-v1` | CTC | `primary` | vocabulary |
| `tdt-v1` | TDT | `encoder`, `predictor`, `joint` | vocabulary |
| `whisper-autoregressive-v1` | Whisper autoregressive | `encoder`, `decoder`, optional `decoder_with_past` | Transformers processor |

profile set:

- `parakeet-tdt-ctc-v1`
  - default: `ctc`
  - variants: `ctc`, `tdt`
- `whisper-autoregressive-v1`
  - default: `whisper`

revision JSONやcandidate metadataでdecoder declarationを重複させません。

## 5. Four-document revision bundle

必須:

```text
reference.json
evaluation-schema.json
datasets-lock.json
runtime.json
```

`runtime.json` はsource-controlled `config/asr-catalog.json` のID/SHAとprofile setをpinします。

`datasets-lock.json` ではload自体にはoptionalなfieldがあっても、execution snapshot生成時には各datasetについて `sha256` と `manifest` が必須です。`subset` / `split` が省略された場合だけtyped execution snapshotで仕様上の `default` に正規化されます。

## 6. Run context

`run-context.json` schema v2はnullable compatibilityを持ちません。

必須identity:

- candidate ID / artifact role / artifact SHA / size
- Git repository / commit / ref / dirty
- host OS / arch / hostname / Python identity
- runtime implementation / ONNX Runtime version / provider
- config version / revision bundle SHA
- dataset SHA / manifest
- resolved config identity
- generated candidate contract

外部から読んだrun-contextもJSON Schemaだけでなくtyped parserでsemantic cross-checkします。

## 7. Metricsとsample result

`metrics.json` と `samples.jsonl` はexecution evidenceなので、一部の観測不能値には `null` が許可されています。これはrun-context identityのnull禁止とは目的が異なります。

例:

- node assignmentを計測していない → `assigned_nodes: null`
- parity runでない → parity numeric fieldsが `null`
- device memoryを計測できない → `peak_device_memory_mb: null`

観測していない値を0やfalseで偽装しません。

## 8. Rust / Python parity

PythonはCTC/TDT/Whisper runtimeを持ちます。Rust evaluatorは現時点でCTCのみです。

このcapability差をmetadataやdocsで埋めません。Rust TDT/Whisper対応を宣言できるのは、multi-session state/KV/feature extractionを実装し、同じgenerated contractで検証できるようになった時点だけです。
