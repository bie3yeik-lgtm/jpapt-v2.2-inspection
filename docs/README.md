# Documentation

この `docs/` は **現行 `main` の実装だけ**を説明します。過去schema、旧runtime-contract、移行互換、将来構想を正本として扱いません。

## 読む順番

1. [architecture.md](./architecture.md) — repository全体の責務とsource of truth
2. [json-contract-design.md](./json-contract-design.md) — human-authored / generated contractの境界
3. [candidate-metadata.md](./candidate-metadata.md) — minimal candidate metadataとstrict inspection
4. [multi-framework-asr.md](./multi-framework-asr.md) — CTC / TDT / Whisperのruntime profile
5. [onnx-export.md](./onnx-export.md) — export/finalizeとcandidate生成
6. [evaluation.md](./evaluation.md) — manifest、run-context、評価
7. [hf-layout.md](./hf-layout.md) / [hf-bucket-operations.md](./hf-bucket-operations.md) — HF Bucket運用
8. [github-actions.md](./github-actions.md) — CI / evaluation workflow
9. [rust-first.md](./rust-first.md) — Rust evaluatorの現在範囲

## 現行契約の重要な不変条件

- `candidate metadata.json` は `profile_set` と `variants` だけを中心とするminimal入力。`schema_version`、candidate ID、hash、tensor binding、decoder configは書かない。
- candidateのruntime-critical値は実artifact、ASR runtime catalog、vocabulary、生成済みmodel/tokenizer configから取得する。
- 値が一意に取得できなければ **推測せずcandidate validationを失敗**させる。
- `runtime-contract.json` はhuman-authored contractではない。
- TDTでは `bos_id`、duration値、predictor state shapeをshapeやblank tokenから補完しない。
- tensor候補が曖昧な場合に「最初のtensor」を選択しない。
- config versionは `reference.json` / `evaluation-schema.json` / `datasets-lock.json` / `runtime.json` の4文書。
- `runtime.json` は必須で、ASR runtime catalogのID/SHAと`profile_set`を固定する。
- `run-context.json` はschema v2のみ。実行時に必要なartifact / Git / host / provider / revision / resolved configをimmutable snapshotとして保存する。
- evaluation manifestはminimal JSONL。`max_duration_sec` は上限非包含として扱う。

## Runtime catalog

再利用可能なASR semanticsの正本は `config/asr-catalog.json` です。

- `ctc-v1`: `primary`
- `tdt-v1`: `encoder`, `predictor`, `joint`
- `whisper-autoregressive-v1`: `encoder`, `decoder`, optional `decoder_with_past`

Parakeet profile set `parakeet-tdt-ctc-v1` は `ctc` をdeployment defaultとし、`tdt`も同じcandidate familyで選択できます。

## Evaluator capability

| evaluator | decoder | provider |
|---|---|---|
| Python ONNX | CTC / TDT / Whisper autoregressive | CPU / CUDA / DirectML / CoreML |
| Rust ONNX | CTC | CPU / CUDA / DirectML / CoreML |

対応可否は文書ではなく `config/evaluators/*.toml` が正本です。
