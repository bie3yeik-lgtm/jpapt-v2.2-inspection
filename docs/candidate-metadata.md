# Candidate Metadata

## 方針

`candidates/<candidate-id>/metadata.json` は、人間が必要最小限の情報だけを記述する入力ファイルとします。

人間が書くのは次の2種類だけです。

```text
profile_set
variant -> artifact role/path
```

必要ならtokenizer/processorの相対pathだけ追加できます。

採番、SHA-256、file size、catalog fingerprint、tensor I/O、token ID、decoder設定など、ファイル・Git・catalog・model configから取得できる値は手書きしません。これらは後段のコードで検査・補完し、`run-context.json`などの生成物へ保存します。

---

## 最小形

Parakeet:

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

Whisper:

```json
{
  "profile_set": "whisper-autoregressive-v1",
  "variants": {
    "whisper": {
      "artifacts": {
        "encoder": "encoder.onnx",
        "decoder": "decoder.onnx",
        "decoder_with_past": "decoder_with_past.onnx"
      },
      "tokenizer": "tokenizer"
    }
  }
}
```

JSON Schema:

```text
evaluation/schemas/candidate-metadata.schema.json
```

---

## 書かない値

```text
schema_version
candidate_id
catalog id / SHA-256
decoder
profile id
artifact_contract
features
artifact SHA-256
artifact size
input/output tensor names
blank/bos/eos/prompt token IDs
TDT durations
predictor state shapes/dtypes
KV-cache names
```

理由:

```text
candidate_id          -> directory名 / allocatorから取得
catalog fingerprint   -> Git/configから取得
artifact SHA/size     -> fileから計算
decoder/profile       -> profile_set + variant + asr-catalogから解決
tensor binding        -> ONNX graphから検査
token IDs             -> tokenizer/model configから検査
state/KV情報          -> graph/model configから検査
```

「人間が決める値」と「機械が観測できる値」を同じJSONへ手入力させないことを優先します。

---

## Candidate tree

```text
candidates/<candidate-id>/
├── README.md
├── metadata.json
├── tokenizer/
└── <variant artifacts>
```

`candidate-id`はCentral Allocatorがdirectory名として決定するため、metadata.jsonへ再記述しません。

---

## Runtime選択

variant名は`config/asr-catalog.json`のprofile setへ対応します。

```text
profile_set = parakeet-tdt-ctc-v1
ctc -> ctc-v1
tdt -> tdt-v1
```

metadata.jsonへdecoder/profileの意味を複製しません。

---

## Generated provenance

後段コードはmetadataと実artifactを読み、必要な値を検査してrun provenanceへ保存します。

```text
candidate_id
profile_set
variant
resolved profile
decoder
artifact contract
catalog fingerprint
artifact SHA-256 / size
variant bundle SHA
resolved graph/tokenizer bindings
```

これらは再現性には必要ですが、人間入力には不要です。

---

## Compatibility

candidate metadata v1/v2の読み取り互換は削除しました。旧schemaを維持する要件はありません。

現在のschemaは「v3を継承した次版」ではなく、不要なversion field自体を人間入力から外したcanonical contractとして扱います。実装側のloader/generatorは後続作業でこのschemaへ合わせます。
