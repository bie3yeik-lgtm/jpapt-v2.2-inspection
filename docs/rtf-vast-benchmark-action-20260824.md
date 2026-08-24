# RTF Vast Benchmark Action

## 目的

`.github/workflows/rtf-vast-benchmark-run.yml`は、先行するVast offer inventoryで得たoffer IDを
入力として、既存のRTF benchmark image・HF fixture・Parakeet benchmark runnerをVast instance上で
実行する。結果はReusable Result Collectionへ渡し、指定した`rtf-score` rootへ保存する。

保存先は次の形式である。

```text
rtf-score/smoke/vast/<gpu>/batch-<1|8|32>/
├── service-result.json
├── metrics.json
├── benchmark-record.json
├── benchmark-summary.json
└── summary.md
```

## 入力

- `offer_id`: `Vast Offer Inventory` artifactの`offer_id`。instance IDではなく、create前のoffer ID。
- `gpu`: inventoryに記録されたGPUラベル。metricsのidentity照合に使用する。
- `pricing_type`: `on-demand`または`bid`。
- `bid_price`: bid利用時のUSD/hour。空値は拒否する。
- `cost_mode`: `guarded`はbatch 1、`full-matrix`は1→8→32を逐次実行する。

## 実行境界

```text
GHCR digest resolve
  -> Resolver fixture/image identity check
  -> Vast offer IDでinstance create
  -> loading/runningをbounded poll
  -> ssh-url取得とSSH readiness確認
  -> /opt/rtf-benchmark/entrypoint.sh
  -> content probe
  -> batch-1/8/32 sequential benchmark
  -> HF fixture repoへmetrics publish
  -> receipt/metrics回収
  -> instance destroy
  -> RTF Service Result Collection
  -> rtf-score/smoke/vast/...
```

各batchは独立したVast instanceで実行し、metricsとreceipt回収後にdestroyする。これにより、
batch間のCUDA状態とinstance課金を持ち越さない。

## Secret

```text
VAST_API_KEY   # offer/create/show/ssh-url/destroy
HF_TOKEN       # fixture取得とmetrics publish
GITHUB_TOKEN   # private GHCR image pull credentialとしてVast createに渡す
```

GitHub Actionsの`github.token`はGHCR package readに限定し、Vast API keyとHF tokenはログへ出力しない。

## Fail-closed条件

- offer IDが数字でない
- digest-pinned imageでない
- fixture pointer/receipt/image digestが不一致
- Vast instanceが`running`にならない
- SSH readiness timeout
- Vastが時間単価を返さない
- content probe失敗
- metrics/receipt未生成

失敗時もblocked receiptを作成し、instanceが作成済みならEXIT trapでdestroyを試みる。

## 公式仕様

- [Vast create instance](https://docs.vast.ai/cli/reference/create-instance)
- [Vast CLI lifecycle](https://docs.vast.ai/cli/hello-world)
- [Vast ssh-url](https://docs.vast.ai/cli/reference/ssh-url)
