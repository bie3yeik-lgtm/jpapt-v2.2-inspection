# jpapt-v2.2-inspection documentation

この`docs/`は、現在の実装だけを正本として説明する。旧Python-first評価、単純JSON比較、単一ONNX前提、nullable parity、未証明Execution Providerを成功扱いする説明は正当な運用として扱わない。

## 正本となる責務分離

```text
Hugging Face / Python
  ├─ exact revision resolution
  ├─ dataset materialization
  ├─ NeMo checkpoint load
  ├─ NeMo→ONNX export/reference evidence generation
  └─ structural schema validation

Rust release CLI: asr-eval
  ├─ generated candidate verification
  ├─ ONNX Runtime execution
  ├─ provider evidence
  ├─ NeMo→ONNX validation bundle acceptance
  ├─ CER/WER authoritative calculation
  └─ NeMo reference ↔ ONNX quality acceptance

Hugging Face Bucket
  └─ immutable-ish development evidence and candidate/run artifacts
```

ASR品質の最終判定はRust `asr-eval`に集約する。PythonはNeMo transcriptを生成するが、NeMo側で計算したCER/WERを品質の正本にはしない。

## 文書一覧

- [architecture.md](architecture.md) — repository / Python / Rust / HF Bucketの責務境界
- [contracts.md](contracts.md) — human-authored / generated / evidence contract
- [hf-buckets.md](hf-buckets.md) — Bucket treeと配置規約
- [hf-bucket-initialization.md](hf-bucket-initialization.md) — 新規Bucket初期化GitHub Actions
- [nemo-onnx-pipeline.md](nemo-onnx-pipeline.md) — NeMo→ONNX→ASR品質測定のcanonical pipeline
- [evaluation.md](evaluation.md) — `asr-eval`評価とNeMo/ONNX品質比較
- [providers.md](providers.md) — CPU/CUDA/DirectML/CoreML証拠規約
- [workflows.md](workflows.md) — GitHub Actions / HF Jobs運用
- [json-reference.md](json-reference.md) — JSON/JSONL標準記入例
- [development.md](development.md) — 開発・CI・破壊的contract更新時のルール

## 重要な不変条件

1. Moving branch名をexecution identityとして保存しない。Hub revisionは実行前にimmutable commit SHAへ解決する。
2. `.nemo`、ONNX、external data、tokenizer、fixtureはSHA256とsizeを持つ。
3. NeMo referenceとONNX export evidenceは同じrepo/revision/`.nemo` SHA256でなければ比較しない。
4. 同じdataset rowであることを配列indexだけで推定しない。sample ID、audio SHA256、ground-truth textを一致させる。
5. Python producerの`normalized_text`を信用しない。Rustが`asr_metrics_v1`で再計算する。
6. NeMoが出したCER/WERを品質判定へ流用しない。NeMo/ONNX双方をRustで同じmetric実装に通す。
7. CTC quality gateとTDT export/state gateを混同しない。Rust TDT runtime/controllerが成立するまでTDT ASR品質測定対応を主張しない。
8. acceleratorのsession registrationをexecution proofと呼ばない。
9. Bucket initializerはreconcilerではない。非空Bucketを保守的に拒否する。
10. compatibility shimより、未使用contractは破壊的に正本へ寄せる。
