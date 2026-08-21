# RTF provider content-first gate

更新日: 2026-08-21

## 目的

RTF benchmarkでは `result/metrics` の公開より先に、HF JobsまたはRunPod上で固定fixtureを読み込み、実際のASR推論結果が取得できることを確認する。metricsはこのcontent gateを通過したprovider実行だけが生成・公開対象になる。

## 実装した契約

```text
GHCR digest image
  -> provider job/pod start
  -> immutable fixture load
  -> one-sample content probe
  -> content.json / Actions artifact
  -> full-batch metrics
  -> HF result upload and service-result collection
```

`content_probe.py` はmanifestの最初のmaterialized audioを1件だけ推論し、model/dataset/fixture/image境界情報と `reference_text` / `hypothesis_text` を `content.json` に保存する。成功時だけentrypointがfull benchmarkを起動する。

## provider別の回収

- HF Jobs: `RTF_CONTENT_PROBE=...` のmachine-readable log行を抽出し、`results/batches/batch-N/content.json` に保存する。
- RunPod: SSH実行後に `/output/content.json` を先に回収し、metricsやreceiptがなくてもcontent probeの失敗証拠をActions artifactに残す。
- どちらもcontent probeが失敗した場合はfull metricsを実行せず、result uploadも行わない。

## 受入条件

`content.json` の `status=completed`、`content_available=true`、および次のidentityが揃うことをprovider contentの受入証拠とする。

- model id/revision
- dataset id/revision
- fixture repository/revision
- manifest SHA-256
- provider/service/GPU
- reference textとhypothesis text

schema正本は `evaluation/schemas/rtf-provider-content.schema.json` である。このartifactはASR品質やRTF値の合格を意味せず、provider上で期待する内容を取得できたことだけを示す。品質・性能・promotionは後段のmetrics/record契約で判定する。

## 現在の残作業

- 実HF Jobsでcontent artifactが取得できることを確認する。
- RunPodでSSH到達後にcontent artifactが取得できることを確認する。
- T4でcontent probe後にbatch 8/32へ進む際のOOMを再評価する。
- provider固有のjob/pod identityと失敗ログをreceiptへ昇格する。

外部providerの実行成功は静的検証だけでは受入完了にできない。実行時のHF_TOKEN/RUNPOD_TOKEN、サービス在庫、GHCR pull権限が必要である。
