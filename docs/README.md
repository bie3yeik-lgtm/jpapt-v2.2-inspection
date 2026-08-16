# Documentation

この `docs/` は、現行実装の **strict execution contract** と Hugging Face Bucket 運用だけを説明する正規ドキュメントです。過去schema、legacy 3-file config、nullable run-context、human-authored runtime binding、将来構想は扱いません。

コード・schema・catalog・workflowと本文が矛盾する場合、実装側を正本とします。

## 読む順番

1. [architecture.md](./architecture.md) — repository全体の責務とデータライフサイクル
2. [contracts.md](./contracts.md) — human-authored / source-controlled / generated の境界
3. [hf-buckets.md](./hf-buckets.md) — 実際のHF Bucket名とtree
4. [json-reference.md](./json-reference.md) — 各JSONファイルの標準形と記入例
5. [evaluation.md](./evaluation.md) — candidate評価、run、benchmark、promotion
6. [providers.md](./providers.md) — CPU/CUDA/DirectML/CoreMLの実行規約
7. [workflows.md](./workflows.md) — GitHub Actions / HF scriptsの運用手順

## 重要な不変条件

- `metadata.json` はcandidateの最小human-authored入力であり、`profile_set` と `variants` を記述する。
- candidate ID、artifact SHA-256、size、catalog fingerprint、tensor binding、decoder configは生成値であり、人が `metadata.json` に書かない。
- runtime semanticsのsource of truthは `config/asr-catalog.json`。
- ID prefixのsource of truthは `config/hf-allocation-catalog.json`。
- config versionは `reference.json` / `evaluation-schema.json` / `datasets-lock.json` / `runtime.json` の4文書で構成する。
- `runtime.json` は必須。legacy 3-file configは現行execution contractでは扱わない。
- fetched configには隣接する `resolved.json` が必須で、`config-NNNNNN` identityを確定する。
- `run-context.json` はschema v2のみ。execution identityに `null` を許さない。
- PythonとRustは同じcandidate/revision/config identityを消費する。
- Rust evaluatorのdecoder対応は現時点でCTCのみ。Python evaluatorはCTC/TDT/Whisper autoregressiveを扱う。
- provider登録成功とprovider実行証明は別物として扱う。
- candidateは中央Allocatorが採番し、candidate prefixへの公開はwrite-once前提で検証する。
- promotionはacceptedな`full` runを標準条件とし、Bucket candidateをversioned HF Model Repoへ移す。

## 現在の主要ターゲット

| target | upstream | profile set | development Bucket | Model Repo |
|---|---|---|---|---|
| `parakeet-tdt_ctc-0.6b-ja` | `nvidia/parakeet-tdt_ctc-0.6b-ja` | `parakeet-tdt-ctc-v1` | `gawohok7/jpapt-v2.2-dev-bucket` | `gawohok7/jpapt-v2.2-dev` |
| `kotoba-whisper-v1.0` | `kotoba-tech/kotoba-whisper-v1.0` | `whisper-autoregressive-v1` | `gawohok7/tf-v1-onnx-dev-bucket` | `gawohok7/tf-v1-onnx-dev` |

Bucketの具体的なtreeは [hf-buckets.md](./hf-buckets.md) を参照してください。
