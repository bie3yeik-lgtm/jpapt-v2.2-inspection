# RunPod CUDA probe gate 作業履歴

## 目的

RTF benchmarkのRunPod選択前に、GPU availabilityだけでなく、実Pod上のGPU名、CUDA Version、
CUDA device、cleanupを検証する。

## 変更

- `run-runpod-cuda-probe.sh`を追加し、一GPUの作成・SSH診断・report・cleanupを実装した。
- inventory workflowにinventory-only／probe-selected／probe-allを追加した。
- RTF選択workflowとRTF benchmark直接起動経路へprobe gateを接続した。
-共有設定のcloud typeをavailability判定へ反映した。
- Recursive Delivery着手エントリーを追加した。

## 検証結果

- JSON、Python、Bash、YAMLの静的検証: 実行済み。
- RunPod probe fixture: 正常系・availability失敗系ともにPASS。
- `cargo run --quiet --locked -p asr-contracts --bin asr-workflow-dispatch -- validate`: PASS。
- `mise run check`: このリポジトリにtaskが存在しないため未実行。
- `mise run lint`: runner環境に`ruff`が存在しないため未完了。
- RunPod実Podprobe: `RUNPOD_TOKEN`と外部GPU状態が必要なため、ローカルでは未実行。
- 未検証の外部サービス状態をPASSとして扱わない。

## 次の安全な作業

1. GitHub Actionsで`inventory-only`を実行する。
2. 低コストな対象GPU一台で`probe-selected`を実行する。
3. artifactのcleanup_statusとPod残存を確認する。
4. 問題がなければRTF benchmarkを一バッチで実行する。
