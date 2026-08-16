# Development

## Local development flow

```text
1. target / runtime variantを選ぶ
2. upstream/referenceをmaterialize
3. ONNX artifactをexport
4. finalizeでminimal metadata.jsonを生成
5. CandidateArtifacts.load()でstrict validation
6. smoke/parity/full evaluationを実行
7. run-context / metrics / benchmarkを保存
8. evidenceを満たしたcandidateのみpromotion
```

## Config hierarchy

```text
config/asr-catalog.json
config/hf-allocation-catalog.json
config/hf-targets/*.toml
config/evaluators/*.toml
config/providers/*.toml
config/environments/*.toml
config/evaluation/*.toml
```

同じ意味をlocal JSONへコピーしません。

## Python

Python packageはcandidate inspection、export/finalize、dataset manifest、evaluation、run-context/HF revision処理を担います。unit testは `.github/workflows/python-unit.yml` で `python/tests/unit` 全体を実行します。

## Rust

Rust workspaceはONNX evaluator/runtimeを提供します。公開capabilityは `config/evaluators/rust-onnx.toml` に従い現在CTCです。provider matrixのbuild/testはRust CIで確認します。

## Candidate変更時の最低確認

- candidate metadata schema
- ASR catalogとのartifact role整合
- tokenizer discovery
- strict ONNX inspection
- CTC/TDT/Whisper該当unit test
- Python full unit
- HF contract validation

## Contract変更

旧schema互換を維持するためのbranchを追加しません。schemaを変更する場合はloader/tests/docsを同時にcanonical contractへ更新します。

## 推測禁止

runtime-critical情報が欠けるcandidateを「とりあえず動かす」ためのfallbackは追加しません。exporterまたはgenerated config側で事実をmaterializeし、inspection側はそれを検証します。
