# Candidate Metadata

`metadata.json` はcandidateの構成だけを指定するminimal human-authored inputです。

## Canonical form

```json
{
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "artifacts": {"primary": "ctc/model.onnx"}
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

`tokenizer` は既定配置から一意に発見できる場合は省略できます。

## 書かない値

- `schema_version`
- `candidate_id`
- catalog ID/SHA
- artifact SHA/size
- decoder/profile/artifact contract/features
- tensor I/O
- blank/BOS/EOS/prompt token IDs
- TDT durations/state metadata
- KV-cache binding

これらは `CandidateArtifacts.load()` がcatalog・artifact・vocabulary・生成済みconfigを検査して生成します。

## Candidate ID

取得済みcandidate rootに `.candidate-id` があればそれを使用し、なければdirectory名を使用します。allocatorは`metadata.json`を書き換えません。

## Tokenizer discovery

Vocabulary profileは既知の `vocabulary.json` / `vocab.json` / `tokens.json` 配置を探索します。Transformers processorは `tokenizer/`, `processor/`, candidate rootの既知configを探索します。曖昧な配置は明示pathを要求します。

## Strict inspection

runtime-critical値を推測しません。

TDTでは特に、BOSをblankで代用しない、duration output shapeからduration値を生成しない、dynamic state shapeを`1`で埋めない、曖昧tensor候補を先頭採用しない、という契約を維持します。

## Provenance

評価時にはcandidate ID、profile set/variant/profile、decoder、artifact contract、catalog fingerprint、bundle SHA、artifact hash/size、tokenizer、features、resolved runtime contractをgenerated provenanceとしてrun-contextへ保存します。
