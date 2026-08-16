# JSON / TOML Contract Design

## 原則

このrepositoryでは、JSON/TOMLを「人間が決める値」と「コードが観測できる値」に分離します。

```text
人間が決める selection / policy
    -> minimal input

artifact / Git / catalog / config / runtimeから取得できる値
    -> code generation / inspection

過去runの再現に必要な値
    -> immutable snapshot
```

同じ意味を複数ファイルへ手入力しません。旧schemaとの読み取り互換も設計目標にしません。

## Human-authored contracts

### Candidate metadata

```json
{
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {"artifacts": {"primary": "ctc/model.onnx"}},
    "tdt": {
      "artifacts": {
        "encoder": "tdt/encoder.onnx",
        "predictor": "tdt/predictor.onnx",
        "joint": "tdt/joint.onnx"
      }
    }
  }
}
```

optional `tokenizer` path以外の生成可能情報は書きません。

### Evaluation manifest

```json
{"dataset_id":"jsut-basic5000","count":6,"seed":"smoke-jsut-v1"}
```

必要なら `min_duration_sec`, `max_duration_sec` を加えます。内部entry ID、stable-hash strategy、filter objectはloaderが生成します。duration条件は `min <= duration < max` です。

## Generated / immutable contracts

### Config version

```text
reference.json
evaluation-schema.json
datasets-lock.json
runtime.json
```

`runtime.json` は必須です。runtime revision snapshotにはcatalog ID/SHAと`profile_set`だけを固定し、decoder semanticsを複製しません。

### Candidate provenance

`CandidateArtifacts.provenance_dict()` がcandidate ID、resolved profile、decoder、artifact contract、catalog fingerprint、artifact hash/size、tokenizer identity、features、resolved runtime contractを生成します。

### Run context

`run-context.json` はschema v2のみです。top-levelにartifact/Git/host/runtime/revisions/resolved config/metadataを持ちます。

`revisions.runtime` は次のcanonical形です。

```json
{
  "document_sha256": "<sha256>",
  "catalog": {"id":"asr-runtime-catalog-v1","sha256":"<sha256>"},
  "profile_set": "parakeet-tdt-ctc-v1"
}
```

reference/evaluation revisionへdecoder listを複製しません。

## Strict derivation

runtime-critical値は「妥当そうな推測」を禁止します。

- CTC blank IDはconfig/metadata/vocabularyから一意に取得する。
- TDT BOSはblank IDで代用しない。
- TDT durationsはduration output shapeから連番生成しない。
- dynamic predictor state dimensionを`1`で埋めない。
- concatenated TDT outputのvocab sizeは明示的sourceを要求する。
- tensor候補が曖昧なら先頭要素を採用しない。
- Whisper prompt/eosが生成済みconfigから得られなければrejectする。

## Contract ownership

```text
runtime semantics       config/asr-catalog.json
candidate layout        candidate-metadata.schema.json
manifest input          manifest.schema.json
run snapshot            run-context.schema.json
resolved observation    Python inspection/runtime code
```

文書にしか存在しないfieldや互換ルールはcontractではありません。
