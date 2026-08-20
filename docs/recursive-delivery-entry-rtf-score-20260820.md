# Recursive Delivery Entry: RTF Score and Service Validation

作成日: 2026-08-20
対象ブランチ: `feat/rtf-score-validation-actions`
適用スキル: `.agents/skills/recursive-delivery-abstruct/SKILL.md`
参照仕様: [`Calculare-RTF-Score.md`](Calculare-RTF-Score.md)

## Objective

`nvidia/parakeet-tdt_ctc-0.6b-ja` の TDT/CTC と
`kotoba-tech/kotoba-whisper-v2.0` を固定 revision、共通音声入力、共通 dataset で
比較し、RTF/RTFx、CER、メモリ、GPU/service 情報を再現可能な検証結果として保存する。
GitHub Actions は実行と結果回収のオーケストレーションに限定し、RTF 算出・結果契約・
集計は Rust-first の既存評価基盤へ統合する。

## Frozen contract

```text
RTF  = total_processing_time / total_audio_duration
RTFx = 1 / RTF
```

個別音声 RTF の平均ではなく、総処理時間と総音声時間から算出する。`RTF_model`
（モデル入力後の推論）と `RTF_service`（decode/resample/前処理/推論/後処理）を分離し、
batch=1 latency と batch throughput を別 identity とする。

共通 dataset:

```text
japanese-asr/ja_asr.common_voice_8_0
japanese-asr/ja_asr.jsut_basic5000
japanese-asr/ja_asr.reazonspeech_test
```

音声は float32、mono、16 kHz、finite、C-contiguous を満たす。model/dataset revision、
manifest、candidate/artifact SHA-256、decoder、provider/service、GPU、dtype、batch、
run identity は結果へ保存する。未観測の provider 実行、GPU telemetry、料金は推測せず
`null` または `not verified` とする。

## Dependency-ordered units

```text
Unit 0  entry / scope / evidence boundary
  -> Unit 1  Rust RTF domain contract and tests
  -> Unit 2  benchmark schema and compatibility
  -> Unit 3  deterministic dataset/audio manifest
  -> Unit 4  Parakeet/Kotoba measurement runners
  -> Unit 5  HF Endpoint/HF Jobs/RunPod adapters
  -> Unit 6  GitHub Actions dispatch/collect/validate/persist
  -> Unit 7  ranking and cost analytics
  -> Unit 8  acceptance report and handoff
```

各 unit は Orient → Define → Prove → Implement → Verify → Accept の順に閉じる。失敗した
unit は fallback で隠して次へ進めず、`blocked` または `not verified` として記録する。

## Current implementation slice

- Rust `asr-metrics` に有限値、正の音声時間、正の処理時間を検証する RTF contract を追加。
- `asr-eval` の aggregate RTF 算出を contract 経由にし、`rtfx` と `rtf_scope=model` を出力。
- benchmark schema は optional な `rtfx` と `rtf_scope` を受理する。
- Python aggregate writer も `rtfx` / `rtf_scope=model` を出力する。
- Rust resolved-manifest validation が duplicate sample ID、非有限 duration、非正 duration を拒否する。
- Python compatibility boundary にも `calculate_rtf` と `RtfMetrics` を追加し、sample/aggregate
  の RTF 算出を同じ contract へ寄せた。
- `.github/workflows/rtf-benchmark-contracts.yml` を追加し、fixed manifest、schema JSON、
  Rust RTF contract を remote execution 前に検証する。
- `rtf-service-result.schema.json` と `asr-rtf-service validate` を追加し、HF/RunPod
  実行結果の status、job、URI、SHA-256、blocked error を共通契約へ固定する。
- `rtf-service-metrics.schema.json` と Rust validator を追加し、dataset revision、manifest
  SHA-256、RTF/RTFx、CER、VRAM、GPU utilization、料金を nullable telemetry として固定する。
- `.github/workflows/rtf-service-result.yml` を追加し、metrics URIから取得したpayloadを
  SHA-256・metrics schemaで検証したうえで、envelopeとmetricsをActions artifactと
  `GITHUB_STEP_SUMMARY`へ保存する。
- `.github/workflows/rtf-verification-select.yml` を追加し、サービス、GPU、model、dataset、
  decoder、batch、run_idを一件ずつworkflow_dispatchで選択し、Phase 1 matrixに照合して
  実行対象selection artifactを保存する。無効な組合せは外部実行前に拒否する。
- `rtf-service-result.yml` は取得したservice envelopeとmetricsを
  `rtf-scores/<run_id>/<service_id>/`へ保存し、Actions botのcommitとして起動ブランチへ
  pushする。Actions artifactにも同じ内容を保存する。
- `dispatch-rtf-service-result.sh` を追加し、既存の bounded workflow dispatch helper を介して
  service-result collection workflow へ送る。
- completed result に `metrics_path` がある場合、`asr-rtf-service validate` が実ファイルの
  SHA-256 と専用の `metrics_sha256` を照合し、metrics schemaも検証する。結果artifactの
  `result_sha256`とは別の証跡として扱う。
- RTF analytics contract に `audio_hours_per_gpu_hour` と
  `cost_per_audio_hour = gpu_price_per_hour * rtf` を追加した。料金未取得時は null とする。
- 3 dataset、実 GPU、外部 service、料金、provider execution proof は未実測。
- `evaluation/manifests/rtf-phase1-matrix.json` に、HF Jobs T4/L4 と RunPod Pod
  A5000/L4/3090/4090、batch 1/8/32 の無効組合せを含まない明示matrixを追加した。

## Acceptance evidence

Unit 1 の受入条件:

- corpus total による RTF/RTFx の deterministic unit test
- zero/negative/NaN/infinity の fail-closed test
- Rust benchmark output の schema compatibility
- `cargo fmt --all -- --check`
- `cargo test --locked -p asr-metrics -p asr-eval`

最終受入では `cargo test --locked --workspace`、`cargo clippy --locked --workspace --all-targets
-- -D warnings`、`cargo fmt --all -- --check`、`mise exec -- uv run pytest -q`、
`git diff --check`、固定 revision の dataset manifest、
named GPU/service の外部実測結果、保存 artifact の SHA-256 を確認する。GitHub-hosted CPU
run は GPU 性能や CoreML/DirectML/CUDA 実行証拠の代替にはしない。

## External boundary and next safe action

HF/RunPod credential、endpoint、GPU allocation がない場合、service adapter unit は
契約・negative test までを受入れ、実サービス結果は `BLOCKED` とする。次は benchmark
schema の既存 Python writer/capsule interop を確認し、Unit 2 を閉じてから deterministic
manifest、runner、Actions の順に進める。

## Implementation evidence (2026-08-20)

完了した範囲:

- `asr-metrics` に fail-closed な `rtf_metrics` / `RtfMetrics` / `RtfError` を追加。
- `asr-eval` の aggregate RTF を共通 contract 経由にし、`rtfx` と `rtf_scope=model` を追加。
- `benchmark.schema.json` が optional `rtfx` / `rtf_scope` を受理するよう更新。
- この文書と `docs/rtf-score-validation-actions.md` の重複契約を整理。

検証結果:

```text
cargo fmt --all -- --check: PASS
cargo test --locked -p asr-metrics -p asr-eval: PASS
cargo clippy --locked -p asr-metrics -p asr-eval --all-targets -- -D warnings: PASS
cargo test --locked -p asr-contracts: PASS
cargo clippy --locked -p asr-contracts --all-targets -- -D warnings: PASS
cargo test --locked -p asr-contracts --test rtf_service: PASS
cargo clippy --locked -p asr-contracts --all-targets -- -D warnings: PASS
cargo test --locked -p asr-contracts --test rtf_service: PASS
rtf-service blocked envelope CLI probe: PASS
service-result dispatch argument rejection probe: PASS
service-result local metrics SHA-256 verification: IMPLEMENTED; runtime probe pending
RTF cost analytics unit test: PASS
workspace Rust tests: PASS
workspace Rust clippy: PASS
benchmark.schema.json parse: PASS
cargo test --locked -p asr-eval -p asr-metrics: PASS
cargo clippy --locked -p asr-eval -p asr-metrics --all-targets -- -D warnings: PASS
python -m compileall -q python/src/parakeet_onnx: PASS
Python RTF direct import: PASS (locked optional dependencies installed)
RTF workflow manifest validation logic: PASS
git diff --check: PASS
```

未検証・blocked:

- `mise run actions-validate`: 既存の `candidate-routing-config-fetch-contracts.yml` が
  `workflow_dispatch` を持たないため FAIL。今回の変更による失敗とは切り分け済み。
- `mise exec -- uv run pytest -q`: PASS (`164 passed`)。
- repository-wide Python Ruff: 既存コードの baseline findings があるため今回の変更の受入れ根拠には使用しない。
- HF/RunPod credential、endpoint、GPU、料金、外部 service RTF、provider execution proof:
  未取得。
- 現環境には GitHub CLI 認証はあるが、HF token、RunPod CLI/API credential、Docker runtime は
  観測できないため、remote provider execution は未実行。

次の安全な unit は Unit 7 の completed service result 集計である。外部サービス実測へ
進む前に、固定 revision、materialized local audio、audio SHA-256、manifest hash を確定する。

## Unit 3 progress: deterministic benchmark manifest

`evaluation/manifests/rtf-phase1.jsonl` を追加し、Common Voice 8 Japanese、JSUT
Basic 5000、ReazonSpeech held-out の 3 dataset を各 12 sample、固定 seed、1〜20 秒の
duration filter で定義した。dataset revision と Parquet/audio materialization は
`datasets-lock.json` と Python HF boundary が authority であり、revision lock 未提供の
まま実行を PASS 扱いしない。

検証:

```text
JSON parse and required-field/static contract: PASS
materialized audio and pinned dataset revision: NOT VERIFIED
```

Unit 3 は manifest 定義まで受入れ可能だが、canonical execution acceptance は固定された
`datasets-lock.json`、resolved manifest、audio SHA-256 の実測が揃うまで open とする。

## Unit 4/5/6 progress: runner contract, service envelope, and preflight workflows

既存の Python ONNX evaluator は model-input-to-transcript の sample timing を使用し、
aggregate は総処理時間/総音声時間を使用するよう共通 RTF 関数へ接続した。service-result
schema と Rust validator は completed と blocked/not_verified の証拠境界を分ける。
`rtf-benchmark-contracts.yml` は外部 service を呼び出さず、remote benchmark の前提契約を
検証する。`rtf-service-result.yml` は provider 結果 envelope を受け取り、検証済み artifact
として保存する。`dispatch-rtf-service-result.sh` が bounded dispatch を担い、completed の
local metrics path がある場合は Rust CLI が SHA-256 を照合する。HF/RunPod の実ジョブ起動と
remote URI retrieval は未検証である。

## Unit 7 progress: deterministic ranking

既存 capsule analytics に `RtfServiceRecord` と `rank_rtf_services` を追加した。completed
かつ対象 metric が存在する record だけを順位へ含め、blocked/not_verified/未計測 record は
結果から除外する。並び順は metric、service ID、run ID の順で固定し、重複 run ID は拒否する。

## Unit 8 acceptance audit

| Requirement | Evidence | Status |
|---|---|---|
| RTF/RTFx corpus formula | Rust/Python unit contracts | PASS |
| fixed three-dataset manifest | `evaluation/manifests/rtf-phase1.jsonl` | STATIC PASS; revision/audio NOT VERIFIED |
| Phase 1 service matrix | `evaluation/manifests/rtf-phase1-matrix.json` | STATIC PASS; execution NOT VERIFIED |
| model/service timing separation | Python evaluator and `rtf_scope` | CONTRACT PASS |
| service result status contract | `rtf-service-result.schema.json`, Rust validator | PASS |
| result/metrics SHA-256 verification | `asr-rtf-service`, `result_sha256`/`metrics_sha256` | CODE PASS; real result NOT VERIFIED |
| metrics payload contract | `rtf-service-metrics.schema.json`, Rust tests | PASS; real payload NOT VERIFIED |
| bounded dispatch and artifact save | `dispatch-rtf-service-result.sh`, workflow | STATIC PASS |
| remote metrics retrieval and validation | `metrics_uri`, SHA-256, metrics schema | CODE PASS; remote URI NOT VERIFIED |
| individual target selection | `rtf-verification-select.yml` | CODE PASS; provider execution NOT VERIFIED |
| repository score persistence | `rtf-scores/<run_id>/<service_id>/` | CODE PASS; real result NOT VERIFIED |
| deterministic ranking | `rank_rtf_services` | CODE PASS; no completed real records |
| HF Inference Endpoint measurement | external credential/endpoint | BLOCKED / NOT VERIFIED |
| HF Jobs measurement | external token, candidate, fixed revisions | BLOCKED / NOT VERIFIED |
| RunPod Pod measurement | RunPod credential/endpoint | BLOCKED / NOT VERIFIED |
| RunPod Serverless measurement | RunPod credential/endpoint | BLOCKED / NOT VERIFIED |
| GPU/CER/VRAM/service RTF evidence | named external runtime | NOT VERIFIED |

The implementation is not a final benchmark PASS. It is a verified contract and orchestration
implementation with external measurement gates explicitly open.

## Final verification boundary

```text
cargo test --locked --workspace: PASS
cargo clippy --locked --workspace --all-targets -- -D warnings: PASS
cargo fmt --all -- --check: PASS
python -m compileall -q python/src/parakeet_onnx: PASS
workflow YAML static parse: PASS
git diff --check: PASS
uv sync --locked --extra datasets --extra onnx --extra dev: PASS
mise exec -- uv run pytest -q: PASS (164 passed)
targeted RTF ruff check/format: PASS for new RTF module and tests
repository-wide Python ruff check/format: NOT PASS (pre-existing baseline findings outside this change)
mise run actions-validate: BLOCKED by pre-existing workflow_dispatch contract failure
named external GPU/service runtime: NOT VERIFIED
```

No commit, push, remote workflow dispatch, HF mutation, or RunPod mutation has been performed
in this local execution. The next safe action requiring external state is to provision the fixed
revision bundle, credentials, immutable benchmark image, and named provider endpoints, then run
each service through `rtf-service-result.yml` and validate the resulting metrics SHA-256.

## 2026-08-20: repository persistence fallback

実行結果が起動元ブランチへ保存されない場合に備え、`.github/workflows/rtf-service-result.yml`
の保存先を `inspection/<run_id>-<service_id>` ブランチへ分離し、`main` 向けPRを自動作成する
よう変更した。既存の同名ブランチとPRは再利用する。`contents: write` に加えて
`pull-requests: write` が必要である。

検証:

```text
git diff --check: PASS
actionlint: NOT VERIFIED (command unavailable on this host)
remote workflow execution and PR creation: NOT VERIFIED
```

## 2026-08-20: Phase 1 GPU combination correction

Actions run `32331959739` の選択値は `runpod-pod / t4 / batch-32` だったが、参照表の対象外
だった。Phase 1 matrixからHF Jobsを除き、対象をHF Inference EndpointのT4/L4とRunPod
 PodのA5000/L4/RTX 3090/RTX 4090の6組へ修正した。選択Workflowのserviceもこの2種類に
限定した。

検証:

```text
matrix JSON parse: PASS
Phase 1 entry count: PASS (6)
runpod-pod/t4 rejection: PASS (not in matrix)
```
