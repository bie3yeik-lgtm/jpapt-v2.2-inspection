# Documentation

この `docs/` は、`main` の現行実装を運用・開発・検証するための正規ドキュメントです。対象は **Rust-first runtime、Python-native ML boundary、Hugging Face Bucket、GHCR reference environment、Execution Provider、GitHub Actions、release/promotion** です。

過去schemaや移行途中の互換経路を正当化する資料ではありません。コード・schema・catalog・workflowと本文が矛盾する場合は、実装・source-controlled contract・workflow YAMLを正本とし、docsを修正します。

## 最初に読む順番

1. [development.md](./development.md) — 現在のtoolchain、ローカル環境、初期セットアップ、日常コマンド
2. [architecture.md](./architecture.md) — repository全体の責務、Rust/Python境界、artifact lifecycle
3. [contracts.md](./contracts.md) — human-authored / source-controlled / generated contract
4. [hf-buckets.md](./hf-buckets.md) — HF Bucketのcanonical layout、legacy read fallback、Model Repoとの役割分担
5. [evaluation.md](./evaluation.md) — candidate評価、run、benchmark、acceptance、promotion
6. [providers.md](./providers.md) — CPU/CUDA/DirectML/CoreMLのprovider evidenceと制約
7. [ghcr-ci.md](./ghcr-ci.md) — Dockerfile→HF target対応、GHCR build/pull/digest/attestation、Bucket評価
8. [github-actions.md](./github-actions.md) — GitHub Actionsのtrigger、input、runner、secret、artifact、用途
9. [github-actions-ux.md](./github-actions-ux.md) — Actionsの操作性、dispatch設計、GitHub UIの制約と改善方針
10. [repository-dispatch.md](./repository-dispatch.md) — 全workflow共通のrepository_dispatch APIとRust入力検証
11. [workflows.md](./workflows.md) — config publish → candidate publish → evaluation → promotion の運用手順
12. [json-reference.md](./json-reference.md) — 主要JSON/JSONL/Parquet contractの標準形
13. [rust-first-migration.md](./rust-first-migration.md) — Rust-first移行の完了状態と、意図的に残すPython boundary
14. [request-execution-identity.md](./request-execution-identity.md) — `request_id` / `request_execution_id` / receipt hash の役割、retry分離、status/timeline query
15. [runtime-estimation.md](./runtime-estimation.md) — provenance cohort、metadata-only candidate workload evidence、runtime estimate v4、size scalingの適用条件
16. [parakeet-provenance-and-routing-responsibility.md](./parakeet-provenance-and-routing-responsibility.md) — Parakeet asset provenance、candidate transfer、親リポジトリとのrouting責務分離
17. [recursive-delivery-entry-20260820.md](./recursive-delivery-entry-20260820.md) — #134 provenance実装のUnit入口・受入条件・blocker
18. [parakeet-provenance-remaining-work-and-parent-contract-20260820.md](./parakeet-provenance-remaining-work-and-parent-contract-20260820.md) — 残作業、受領payload、親リポジトリとの契約、完了判定
19. [recursive-delivery-entry-rtf-benchmark-completion-20260821.md](./recursive-delivery-entry-rtf-benchmark-completion-20260821.md) — RTF Benchmark完成branchの目的、工程、blocker
20. [rtf-benchmark-flow-and-actions-contract-20260821.md](./rtf-benchmark-flow-and-actions-contract-20260821.md) — GHCR、Resolver、provider、record、rank、Actionsの一連の契約
21. [rtf-profile-and-probe-contract-20260821.md](./rtf-profile-and-probe-contract-20260821.md) — `smoke` / `pref` / `probe` の現行profileとprobe規模契約
22. [rtf-smoke-matrix-ranking-objective-20260821.md](./rtf-smoke-matrix-ranking-objective-20260821.md) — 0〜100 users向け全組み合わせsmoke、上位3位ランキング、後続API/モデル改善試験
23. [rtf-benchmark-operational-flow-20260821.md](./rtf-benchmark-operational-flow-20260821.md) — GHCR、Resolver、HF/RunPod smoke、result/metrics回収、ranking PRの現行実行順序
24. [rtf-benchmark-action-run-evidence-20260821.md](./rtf-benchmark-action-run-evidence-20260821.md) — GitHub Actions実run結果とRTF Benchmark未達事項
25. [rtf-provider-service-investigation-20260821.md](./rtf-provider-service-investigation-20260821.md) — HF Jobs / RunPodの実run失敗境界とprovider adapter調査
26. [parent-external-dispatch-workflows-20260820.md](./parent-external-dispatch-workflows-20260820.md) — 親 `repository_dispatch` 向け workflow 実装ブランチの目的、#134/#154/#160 対応、実装 backlog
27. [recursive-delivery-entry-parent-external-dispatch-20260820.md](./recursive-delivery-entry-parent-external-dispatch-20260820.md) — 上記ブランチの recursive delivery 着手入口
28. [parent-repository-external-dispatch-config-handoff-20260820.md](./parent-repository-external-dispatch-config-handoff-20260820.md) — 公開正本 merge 後に親 repo で行う route config 更新 handoff

## 現在の実装スタック

| 層 | 現行実装 |
|---|---|
| Tool version management | `mise.toml` |
| Python | Python `>=3.12,<3.15`; local miseは `3.14`; CIは主に `3.12` |
| Python package/environment | `uv`, `pyproject.toml`, `uv.lock` |
| Rust | Rust `1.97.1`, edition 2024, workspace resolver 3 |
| Rust runtime | `ort = 2.0.0-rc.13` |
| Python ORT | `onnxruntime == 1.28.0` |
| HF client | `huggingface_hub == 1.24.0` をlocked環境で使用。workflowによって公式CLIをpip installして使用 |
| Dataset acquisition | Python `datasets` boundary |
| Persistent analytical run format | `ExperimentCapsuleV1` / Parquet (`asr-capsule`) |
| CI | GitHub Actions |
| Actions dispatch validation | Rust `asr-workflow-dispatch` |
| Reference/export environment registry | GitHub Container Registry (GHCR), digest-pinned |
| Development artifact store | Hugging Face Buckets |
| Release artifact store | Hugging Face Model Repo + Rust binaryはGitHub Releases |

## Rust workspace

```text
rust/crates/
├── asr-contracts   # schema/config/revision/run-context/HF/Actions policy boundary
├── asr-hf          # target routing, Bucket layout, allocation, response bookkeeping
├── asr-audio       # audio decode/resample/canonical waveform
├── asr-runtime     # ONNX Runtime / Execution Provider
├── asr-metrics     # normalization/CER/WER/telemetry
├── asr-eval        # canonical Rust evaluator
└── asr-capsule     # ExperimentCapsuleV1 Parquet read/write/validation
```

Rust evaluatorのdecoder capabilityは現時点で **CTCのみ**です。Python runtimeはCTC/TDT/Whisper autoregressiveを扱います。provider対応とdecoder対応は別軸です。

## 主要なsource of truth

| ファイル | 役割 |
|---|---|
| `config/asr-catalog.json` | decoder profile、artifact roles、tokenizer kind、profile set、default variant |
| `config/hf-targets/*.toml` | profile set + Bucket + Model Repoという最小routing入力 |
| `config/models/*.toml` | model固有execution semantics / provider compatibility |
| `config/providers/*.toml` | provider/session条件 |
| `config/environments/*.toml` | Linux / Windows / macOS環境条件 |
| `config/evaluation/*.toml` | smoke/parity/coreml-parity/full評価条件 |
| `config/evaluators/*.toml` | evaluator capability |
| `evaluation/schemas/*.schema.json` | persisted JSON/JSONL artifact schema |
| `.github/workflows/*.yml` | GitHub UI/manual input schemaとexecution orchestration |
| `docker/*/Dockerfile` labels | GHCR package/source framework/source model/reference-environment identity |

## 現在のHF target

| target | upstream | profile set | development Bucket | Model Repo |
|---|---|---|---|---|
| `parakeet-tdt_ctc-0.6b-ja` | `nvidia/parakeet-tdt_ctc-0.6b-ja` | `parakeet-tdt-ctc-v1` | `gawohok7/jpapt-v2.2-dev-bucket` | `gawohok7/jpapt-v2.2-dev` |
| `kotoba-whisper-v1.0` | `kotoba-tech/kotoba-whisper-v1.0` | `whisper-autoregressive-v1` | `gawohok7/tf-v1-onnx-dev-bucket` | `gawohok7/tf-v1-onnx-dev` |
| `kotoba-whisper-v2.2` | `kotoba-tech/kotoba-whisper-v2.2` | `whisper-autoregressive-v1` | `gawohok7/tf-v2.2-onnx-dev-bucket` | `gawohok7/tf-v2.2-onnx-dev` |

HF target TOMLへupstream/frameworkを重複記入しません。target IDはファイル名、model identity/upstream/frameworkはmodel config、runtime profile/decoderはASR catalogから導出します。

## 重要な不変条件

- candidateのhuman-authored入力は `metadata.json` の `profile_set` とvariant artifact path/tokenizer pathだけに寄せる。
- candidate ID、artifact SHA/size、bundle SHA、catalog fingerprint、tensor binding、decoder configはgenerated value。
- allocation prefixはcollectionから導出する: `candidates -> candidate`, `experiments -> experiment`, `config -> config`。
- `config/hf-allocation-catalog.json` は存在しない。prefix用JSONを復活させない。
- 新規candidateは `candidates/candidate-NNNNNN/` へ書く。`candidates/<variant>/candidate-NNNNNN/` はhistorical read-only fallback。
- candidate ID省略時はBucket listingからresolverが最新candidateを選ぶ。canonicalが存在すればcanonicalを優先する。
- config versionは4文書 (`reference.json`, `evaluation-schema.json`, `datasets-lock.json`, generated `runtime.json`)。
- fetched configには `.ci/hf/config/resolved.json` が必要。
- `run-context.json` schema v2のexecution identityに `null` を許さない。
- candidate protocolでは `request_id` をlogical correlation、`request_execution_id` を1回のGateway/V2 executionとして分離し、同じ `request_id` のretryをexecution単位で永続化・照会する。
- runtime estimatorのcandidate/dataset/package sizeは観測evidenceであり、検証済みprediction modelが導入されるまで `estimate_minutes` へ直接scaleしない。
- GHCR tagは実験identityではない。評価前にRepoDigestへ固定し、`metadata.ghcr.digest`へ記録する。
- `HF_TARGETS_JSON` はGHCR CIでsource-controlled target routingと一致することを検査し、独立したruntime authorityにはしない。
- `workflow_dispatch.inputs` をGitHub UI/manual inputの正本とし、repository dispatch用に別input catalogを作らない。
- repository dispatchはRustがworkflow YAMLからrequired/default/type/choiceを解決し、不正requestをheavy job前に拒否する。
- provider registration、session creation、successful inference、provider execution proof、node assignment proofを別々に扱う。
- DirectML/CoreMLをLinux GHCR containerで評価済みと扱わない。
- accepted `full` runがpromotionの標準条件。
- GitHub Actionsはruntime semanticsを独自定義せず、Rust CLI / source-controlled config / schemaを呼び出すexecution layerとする。

## GitHub Actionsの分類

| 分類 | workflow |
|---|---|
| 常設PR/Push CI | `python-unit.yml`, `rust-ci.yml`, `validate-hf-layout.yml`, `capsule-interop.yml` |
| GHCR contract/build | `ghcr-contracts.yml`, `ghcr-build-publish.yml` |
| GHCR evaluation/audit | `ghcr-evaluate.yml`, `ghcr-audit.yml` |
| 手動評価 | `cpu-full-eval.yml`, `cross-platform-parity.yml`, `rust-eval.yml` |
| provider proof | `provider-strict-probes.yml` |
| public/reference E2E | `public-model-e2e.yml` |
| HF allocation service | `hf-central-allocator.yml` |
| external dispatch | `repository-dispatch.yml` |
| release | `rust-release.yml` |

正確なdispatch対象一覧は文書へ手書きせず、次で取得します。

```bash
mise run actions-list
```

詳細は [github-actions.md](./github-actions.md)、[github-actions-ux.md](./github-actions-ux.md)、[repository-dispatch.md](./repository-dispatch.md)、[ghcr-ci.md](./ghcr-ci.md) を参照してください。

RTF provider content gateの詳細は [rtf-provider-content-first-gate-20260821.md](./rtf-provider-content-first-gate-20260821.md) を参照してください。

`asr-rtf-rank`とHF/RunPod result/metrics受領契約の正本は [asr-rtf-rank-provider-result-contract-20260821.md](./asr-rtf-rank-provider-result-contract-20260821.md) です。

GHCR build/publish完了後のRTF Resolver連続実行契約は [rtf-benchmark-flow-and-actions-contract-20260821.md](./rtf-benchmark-flow-and-actions-contract-20260821.md) の「GHCR publish to RTF Resolver chain」を正本とします。

ローカルでのDockerfile・HF Jobs・RunPod adapter検証は [rtf-local-provider-adapter-test.md](./rtf-local-provider-adapter-test.md) を参照してください。

RTF providerのローカル検証成果、外部証拠境界、次のrecursive unitsは [recursive-delivery-prep-rtf-provider-local-verification-20260821.md](./recursive-delivery-prep-rtf-provider-local-verification-20260821.md) を参照してください。

Rust契約・ログ分類とPython provider/Docker実行の責務分離、VSDD実装順は [rtf-rust-contract-python-provider-implementation-plan-20260821.md](./rtf-rust-contract-python-provider-implementation-plan-20260821.md) を参照してください。

HF/RunPodの実行前cost guard、guarded/full-matrix、timeout、cleanup方針も同資料を正本とします。

これまでのRTF障害、再発防止条件、Dockerfile/GHCR、空値、OOM、provider仕様、VSDD受入条件を統合した計画参考資料は [rtf-complete-reliability-and-cost-planning-reference-20260821.md](./rtf-complete-reliability-and-cost-planning-reference-20260821.md) です。

## 変更時の原則

contract・routing・runtime policyを変更するときは、まずRust/source-controlled contractを変更し、次にPython compatibility/reference boundary、最後にdocsを合わせます。CIを通すためにlegacy parser、nullable identity、二重authorityを戻してはいけません。
