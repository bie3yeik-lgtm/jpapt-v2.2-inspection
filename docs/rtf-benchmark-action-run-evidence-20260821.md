# RTF Benchmark GitHub Actions 実run証拠

確認日: 2026-08-21
対象repository: `bie3yeik-lgtm/jpapt-v2.2-inspection`
確認方法: `gh run list`、`gh run view --json`、`gh run view --log-failed`

この資料は、workflowの静的な存在確認ではなく、GitHub Actionsに保存された実runの状態を記録する。`success`のworkflow完了は、実GPU推論・metrics永続化・ranking受入れの成功を意味しない。

## 結論

2026-08-20の直近RTF実runでは、Resolverは成功したが、HF Jobsの実推論は全batchで完了recordを生成できなかった。したがって、現時点でPhase 1のaccepted benchmark結果、ranking入力、Full移行条件は未成立である。

## 実run一覧

| workflow | run | 結果 | 確認内容 |
|---|---:|---|---|
| RTF Resolver | [32414089663](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32414089663) | success | digest、dataset revision、manifest、fixture revisionの生成jobは成功 |
| RTF Benchmark Run | [32414647326](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32414647326) | failure | HF Jobs T4、batch 1はCUDA illegal memory access、batch 8/32はCUDA OOM。全batch失敗 |
| GHCR Environment Evaluation | [32414047898](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32414047898) | failure | CPU evaluationがrun-contextを生成せず、GHCR evidenceはartifact内に留まった |
| RTF Resolver | [32409407486](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32409407486) | success | Resolver単体は成功 |
| RTF Benchmark Run | [32409761260](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32409761260) | success | workflow jobはsuccessだが、collectされたbatch 1/8/32は全て`blocked` / `PROVIDER_EXECUTION_FAILED` |
| RTF Benchmark Run | [32593711141](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32593711141) | failure | Repository Secret経由のHF T4。fixture/model/image解決とcontent probeは成功したが、batch 1全件推論で`BENCHMARK_INFERENCE_FAILED` / CUDA illegal memory access。guarded policyにより8/32は未実行 |
| RTF Benchmark Run | [32595956141](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32595956141) | success | 修正後のHF T4。batch 1はmetrics/receipt/benchmark recordまでcompleted。batch 8はtyped CUDA OOM、batch 32はcost guard停止。Actionはblocked collectionを正常化してsuccess |
| GHCR Environment Evaluation | [32409358954](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32409358954) | failure | CPU evaluationがrun-contextを生成せず、GHCR evidenceはartifact内に留まった |
| RTF Benchmark Contracts | [32414623783](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32414623783) | failure | `evaluation/manifests/rtf-phase1.jsonl` 1行目でunknown field。workflowの想定schemaと実manifestが不一致 |

## 直近RTF Benchmark Runの詳細

対象run: [32414647326](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32414647326)

### Resolver入力・identity

```text
model_id: nvidia/parakeet-tdt_ctc-0.6b-ja
model_revision: 44edb27eea9317daf89333e75eb830db4b1cc298
dataset_revision: bf8819e8d9a5feb51b0c718686bd20ea67a3c729
fixture_repo_id: gawohok7/rtf-benchmark-fixtures
fixture_revision: 8d2c866ee315bdbed468b2e92e4587d85b6a5cc8
manifest_sha256: 9c47976f6101ebca1fc2575d46fde80d9a33dbc14b1e1f6dc2ca9aeb57a87694
image_digest: sha256:317da2168f22a94a02b988060f0d13d759d745cced90560197963c6ddbebbaba
service_id: hf-jobs
gpu: t4
provider: cuda
inspection_profile: lough
repeat: 3
sample_count: 21
```

### Batch別結果

| batch | status | 実際のエラー | record化 |
|---:|---|---|---|
| 1 | blocked | `CUDA error: an illegal memory access was encountered`。HF Jobはexit code 134で終了し、`RTF_RESULT_RECEIPT`を出力しなかった | 不可 |
| 8 | blocked | `CUDA out of memory`。14.74 GiB中1.53 GiB free、2.71 GiB allocation失敗 | 不可 |
| 32 | blocked | `CUDA out of memory`。14.74 GiB中2.48 GiB free、7.12 GiB allocation失敗 | 不可 |

全batch失敗のためBenchmark jobは最終的にexit code 1となった。collect job自体はblocked envelopeを保存する責務を完了したが、これはbenchmark成功やprovider性能証拠ではない。

## 確認できた問題と次の対応

1. T4向けParakeet TDT実行がbatch 1でCUDA illegal memory accessを起こしている。まずbatch 1の再現条件、CUDA/PyTorch/NeMo image identity、jobログを固定して原因を切り分ける。
2. batch 8/32はT4のメモリ容量に対してOOMである。batch sizeを減らすだけではPhase 1の比較条件を変更するため、T4 laneの許容条件またはモデル実装・allocator設定を明示的に決める必要がある。
3. `rtf-phase1.jsonl`の実manifestはworkflowが期待する旧形式と一致していない。manifest schemaを現行Resolver出力へ合わせるか、Resolverがcanonical manifestを生成する責務を明確にする。
4. GHCR Environment EvaluationはCPU評価を完了recordへ接続できていない。run-context欠落をwarningで終わらせず、canonical evidenceとして採用不可にする現在の扱いを維持する。
5. Resolver successだけでは次工程の実行受入れに進めない。manifest、fixture、image digest、provider実測、metrics SHAの全identityが揃うまで`blocked`とする。

## Evidence boundary

- GitHub Actionsのworkflow/job/log: external service evidence
- Resolver success: resolver execution evidence。benchmark execution successではない
- `RTF Benchmark Run` job success: receipt collectionの完了を含む場合があるが、completed provider resultを意味しない
- `cargo test`やcontract workflow: source/contract evidence。実GPU・GHCR評価・HF fixtureの受入れ代替ではない

次の安全な作業単位は、manifest schema mismatchを解消したうえで、T4 batch 1の失敗を同一digest・同一fixture identityで再現することである。
