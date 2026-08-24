# RunPod CUDA probe gate 作業履歴

## 目的

RTF benchmarkのRunPod選択前に、GPU availabilityだけでなく、実Pod上のGPU名、CUDA Version、
CUDA device、cleanupを検証する。

## 変更

- `run-runpod-cuda-probe.sh`を追加し、一GPUの作成・SSH診断・report・cleanupを実装した。

## 低スペックPod向けの待機・監視・失敗ログ

- probe Podの安全終了期限を既定15分から24時間へ延長し、作成待ちを最大30分、SSH readinessを最大1時間にした。
- benchmark Podは作成後からmetrics・receipt取得まで30秒周期で`pod get`と`pod list`を確認するwatchdogを実行し、Pod消失・停止を3回連続で検知した場合に失敗理由をログへ出す。
- `pod create`、readiness各API、`ssh info`、リモートbenchmark、metrics/receipt取得について、終了コード、Pod ID、応答本文の最大2000文字をActions logへ出力する。
- metrics・receipt取得後、または内部エラー・signal時は既存のcleanup trapを通じてPodを削除する。
- RunPod公式CLIに作成後の`--terminate-after`更新操作はないため、heartbeatによるタイマー更新ではなく、長い安全期限と明示的cleanupで実装した。
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
