# RTF Benchmark 現行実行フローの正本化

## 目的

RTF Benchmarkを実際に行う順序を、GHCR digest発行、Resolver、HF/RunPod smoke、result/metrics
回収、上位3位ranking、ranking PR、後続API/モデル改善試験まで一続きの運用資料に整理した。

## 変更

- `docs/rtf-benchmark-operational-flow-20260821.md`を追加。
- `docs/README.md`から現行フロー資料へリンク。
- 現行Benchmark RunはHF Jobs / RunPodのsmokeに限定し、ローカルGPU smokeを受入条件から除外。

## Evidence

- Source/static: workflow、schema、manifest、Docker entrypoint、result/ranking contractを確認。
- 未検証: GHCR remote digest、HF Dataset publish、HF Jobs / RunPod実GPU実行、ranking PRの外部Actions。

## 次の安全な作業

この文書を実装・PRレビューの入口とし、外部providerでsmoke matrixを実行する。provider結果が
揃うまで最適サービスやbootstrap URL配布の成功を確定しない。
