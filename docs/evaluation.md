# Evaluation

## 入力

評価のhuman-authored dataset selectionは `evaluation/manifests/*.jsonl` です。

```json
{"dataset_id":"jsut-basic5000","count":6,"seed":"smoke-jsut-v1","min_duration_sec":1.0,"max_duration_sec":15.0}
```

必須は `dataset_id`, `count`, `seed`。duration filterは任意です。

`ManifestLoader` は内部でstable-hash selection、entry ID、filter objectへ展開します。durationは `min_duration_sec <= duration < max_duration_sec` です。

## Evaluation profiles

policyは `config/evaluation/*.toml` が正本です。

- `smoke`
- `parity`
- `coreml-parity`
- `full`

## 実行前gate

評価前に次を解決します。

```text
target
profile_set + runtime variant
candidate artifacts
resolved runtime contract
evaluator capability
provider/environment/evaluation config
revision bundle
```

evaluatorがdecoder/artifact contract/provider/featuresを公開していなければ実行しません。

## Run context

`run-context.json` はschema v2のみです。実行時の事実をimmutable snapshotとして保存します。

主な要素:

```text
artifact identity
Git identity
host identity
runtime/provider identity
config identity + resolved config
revision bundle
candidate/runtime provenance metadata
```

revision bundleは `runtime.json` を必須とし、runtime snapshotへcatalog ID/SHAとprofile setを固定します。decoder semanticsをreference/evaluation revisionへ複製しません。

## 出力

run単位では少なくとも次を扱います。

```text
run-context.json
samples.jsonl
metrics.json
promotion.json   # promotion時
```

benchmarkはcandidate/environment-provider/runの履歴としてBucketへ保存します。

## Parity

parityは「ONNX graphがloadできる」だけではなく、reference outputとの数値/ASR品質差、provider executionの成立、fallbackの有無を評価します。CoreML等provider固有の失敗はdecoder/schemaの失敗と混同しません。
