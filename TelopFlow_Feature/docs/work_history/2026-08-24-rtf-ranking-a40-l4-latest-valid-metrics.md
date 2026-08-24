# RTF Ranking A40/L4・最新有効metrics対応

## 目的と範囲

RTF BenchmarkのRunPod候補へA40を追加し、既存のL4を選択可能な全経路へ揃える。
`benchmark-ranking.yml`は指定profile配下を再帰走査し、metrics sidecarが存在・完了・SHA一致する
recordだけをRust rankerへ渡す。各`service_id/gpu/batch_size`セルでは、完成済みrecordのうち
`completed_at`が最新のものだけを採用する。

## 変更

- `.github/workflows/rtf-benchmark-run.yml`: `a40`をdispatch/matrix契約へ追加。
- `.github/workflows/rtf-verification-select.yml`: `a40`を選択肢へ追加。
- `scripts/run-benchmark.sh`: `a40 -> NVIDIA A40`を追加。
- `.github/workflows/rtf-service-result.yml`: A40の表示名を追加。
- `evaluation/manifests/rtf-phase1-matrix.json`: RunPod A40 entryを追加。
- `rust/crates/asr-contracts/src/rtf_cost.rs`: RunPod A40を許可。
- `.github/workflows/benchmark-ranking.yml`: `rtf-scores/<profile>`全再帰走査、metrics sidecar検査、
  除外理由の永続化。
- `docs/asr-rtf-rank-provider-result-contract-20260821.md`: sidecarと最新有効metrics契約を明文化。

## 受入契約

- A40のRunPod正式GPU IDは`NVIDIA A40`。
- L4はHF Jobs/RunPod双方で既存の正式IDを維持する。
- `metrics.json`が存在しない、SHA-256がrecordと不一致、JSON objectでない、または
  `status != completed`のrecordはranking対象外。
- blocked/not_verifiedは新しくても、完成済みmetricsを置き換えない。
- batch 1/8/32は比較単位として保持し、各batchセルで最新の有効recordを採用する。

## 検証

実行予定・実績は変更後の最終報告に記録する。remote HF/RunPod実行は本変更では起動しない。

- `cargo fmt --all -- --check`
- `cargo test --locked -p asr-contracts`
- `bash -n scripts/run-benchmark.sh`
- `git diff --check`

## 未検証・ロールバック

- A40の実在capacity、実測RTF、実請求額はRunPod実行時まで未検証。
- 既存のA5000/L4/3090/4090のartifactは変更しない。
- A40追加だけを戻す場合は、上記A40 mapping・matrix・選択肢を除去すればよい。
