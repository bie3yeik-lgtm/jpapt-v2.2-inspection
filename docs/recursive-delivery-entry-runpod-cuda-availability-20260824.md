# Recursive Delivery Entry: RunPod CUDA availability gate

作成日: 2026-08-24
対象branch: `feat/runpod-cuda-availability-gate`
目的: RTF benchmarkの実行対象RunPod GPUについて、現在のavailabilityと実ホスト上のCUDA要件を確認し、結果をGitHub Actionsからmachine-readableに出力する。

## 完了条件

- 在庫確認とCUDA実証を`PASS`、`FAIL`、`BLOCKED`に分離する。
- `PASS`は、対象GPUのavailability、指定cloud、Pod作成時CUDA下限、`nvidia-smi`、GPU名、CUDA Version、cleanup成功をすべて満たす場合だけとする。
- `rtf-verification-select.yml`と`rtf-benchmark-run.yml`は、RunPod選択時に対象GPUのprobe成功を要求する。
- inventory-onlyではPodを作成せず、明示的なprobeモードだけが課金対象のPodを作成する。
- 成功・失敗・キャンセルのすべてでprobe Podを削除し、cleanup結果をreportへ残す。
- token、HF token、registry credentialをログ・summary・artifactへ出さない。

## 依存順の作業単位

### Unit 0 — SA/PM: authorityと契約の固定

根拠は`AGENTS.md`、`evaluation/manifests/rtf-phase1-matrix.json`、既存の
`scripts/run-benchmark.sh`、RunPod公式の`runpodctl gpu list`とPod作成仕様である。
対象はRunPod PodのCUDA経路だけで、HF Jobs、Vast、CoreML、DirectMLは対象外とする。

共有設定`.github/runpod-rtf-services.json`をGPU論理名、RunPod GPU ID、cloud type、
minimum CUDA versionの正本とする。GitHub Actionsのchoice optionsは動的変更できないため、
静的unionをUIに置き、実行時live gateを実際の選択判定とする。

### Unit 1 — PG: 在庫とポリシーの結合

`scripts/ci/check-runpod-rtf-services.py`でRunPod inventoryと共有設定を結合する。
availability、Secure／Community、CUDA要求、selectableをGPUごとにJSON化する。
設定されたcloud type以外の在庫はselectableにしない。

probe個別結果は`evaluation/schemas/runpod-cuda-probe.schema.json`で検証可能な契約とする。

最小検証:

```bash
python -m json.tool .github/runpod-rtf-services.json >/dev/null
python -m py_compile scripts/ci/check-runpod-rtf-services.py
```

### Unit 2 — PG: 実Pod CUDA probe

`scripts/ci/run-runpod-cuda-probe.sh`は一GPUを対象に次を実施する。

1. inventoryでavailabilityとcloud typeを確認する。
2. `runpodctl pod create`にGPU ID、digest-pinned image、`--min-cuda-version`、SSH、15分の終了期限を渡す。
3. SSH情報を最大5分待つ。
4. Pod上の`nvidia-smi`出力から要求GPU名を確認する。
5. `CUDA Version`を取得し、minimum CUDA version以上か比較する。
6. `/dev/nvidia0`の存在を確認する。
7. reportを出力する。
8. EXIT／INT／TERM／HUPでPodを削除する。

失敗コードは`RUNPOD_GPU_NOT_AVAILABLE`、`RUNPOD_CUDA_REQUIREMENT_UNSATISFIED`、
`RUNPOD_POD_CREATE_FAILED`、`RUNPOD_SSH_FAILED`、`RUNPOD_NVIDIA_SMI_FAILED`、
`RUNPOD_CUDA_RUNTIME_FAILED`、`RUNPOD_CLEANUP_FAILED`などに分類する。

### Unit 3 — PG: inventory workflow

`.github/workflows/runpod-rtf-service-inventory.yml`は次のモードを持つ。

- `inventory-only`: Podを作成せず、在庫と設定だけを確認する。
- `probe-selected`: 指定GPU一台を実証する。
- `probe-all`: 設定済みGPUを順に実証する。

report、個別probe、inventory、summaryをartifactへ保存する。`probe-all`は一台でも失敗したら
workflowを失敗にし、各GPUの個別結果は失わない。

### Unit 4 — PG: RTF選択・実行への連動

`rtf-verification-select.yml`はRunPod選択時にGHCRのbenchmark image digestを解決し、
選択GPUのprobeを実行してからselection artifactを発行する。

`rtf-benchmark-run.yml`は直接起動経路でも同じprobeを実行する。minimum CUDA versionは
workflow内に重複記載せず、共有設定から読む。

probe成功reportは`.ci`に保持し、既存benchmark receiptとは混同しない。benchmark本体の
provider実行成功、metrics、ranking受入れは別の証拠レベルとして扱う。

### Unit 5 — Debug/PM受入れ

確認事項:

- unavailable GPUがprobeを開始せず拒否される。
- Secure／Communityの不一致が拒否される。
- CUDA version不足が拒否される。
- GPU名不一致が拒否される。
- Pod作成失敗時に孤児Podを名前検索して削除する。
- SSH timeout時にPodが削除される。
- cleanup失敗時はPASSにしない。
- credentialが出力されない。
- `workflow_dispatch`直接起動でもlive gateが働く。

## 検証コマンド

```bash
bash -n scripts/ci/run-runpod-cuda-probe.sh
bash -n scripts/run-benchmark.sh
python -m py_compile scripts/ci/check-runpod-rtf-services.py
python -m json.tool .github/runpod-rtf-services.json >/dev/null
git diff --check
mise run check
```

実RunPod検証は`RUNPOD_TOKEN`、digest-pinned GHCR image、利用可能な残高がある場合だけ行う。
外部サービス未実行の状態は`not verified`として記録し、ローカルfixture検証を実サービス成功の
代わりに扱わない。

## rollbackとコスト保護

通常の定期実行は`inventory-only`とする。probeは手動またはRTF実行前に限定する。
probeは15分のterminate期限、5分のSSH待機、60秒の診断timeoutを持つ。cleanup失敗時は
reportのPod IDを使って手動削除し、成功rankingへ進めない。

参照:

- [RunPod runpodctl GPU](https://docs.runpod.io/runpodctl/reference/runpodctl-gpu)
- [RunPod runpodctl Pod](https://docs.runpod.io/runpodctl/reference/runpodctl-pod)
- [RunPod GraphQL manage Pods](https://docs.runpod.io/sdks/graphql/manage-pods)
- [GitHub workflow_dispatch inputs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
