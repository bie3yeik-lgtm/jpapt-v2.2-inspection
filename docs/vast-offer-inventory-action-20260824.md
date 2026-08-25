# Vast offer inventory GitHub Action

## 目的

`.github/workflows/vast-offer-inventory.yml`は、Vast API/CLIでサポートされる検索条件を組み合わせて、
現在レンタル可能な offer を読み取り専用で検索する workflow である。
instance の作成・停止・破棄は行わない。

## 固定条件

次の条件は workflow 入力として表示せず、常に検索クエリへ含める。

```text
verified=true
rentable=true
cuda_max_good>=13
disk_space>=50
```

ユーザー入力が 3 件未満のときだけ、追加で `gpu_arch=nvidia` を含める。
Vast の検索条件数上限に近づく場合は `gpu_arch` を除外し、固定 4 条件 + 任意入力のみで検索する。

## 任意入力

| 入力 | 例 | 生成例 |
|---|---|---|
| `gpu_name` | `RTX_4090` | `gpu_name=RTX_4090` |
| `gpu_name` | `RTX_4090,RTX_3090` | `gpu_name in [RTX_4090,RTX_3090]` |
| `num_gpus` | `1` | `num_gpus=1` |
| `num_gpus` | `>=2` | `num_gpus>=2` |
| `num_gpus` | `in [1,2,4]` | `num_gpus in [1,2,4]` |
| `gpu_ram` | `>=48` | `gpu_ram>=48` |
| `duration` | `>=3600` | `duration>=3600` |

`pricing_type` は `bid` または `on-demand` を選択する。
`storage_gb` は Vast CLI の `--storage` に渡す割当ディスク容量 (GiB) である。
`limit` は返却件数上限である。

## 出力

Actions artifact `vast-offers-<run_id>` に次を保存する。

```text
vast-cli-version.txt
vast-offers/search-query.json
vast-offers/search-query.txt
vast-offers/search-<pricing>.json
vast-offers/inventory.json
vast-offers/inventory.csv
vast-offers/inventory.md
```

一覧には次を含める。

- offer/instance 作成に使う `offer_id`
- `machine_id`, `gpu_name`, `gpu_ram_gb`, `num_gpus`
- `reliability`, `dlperf`, `driver_version`, `direct_port_count`
- `cuda_max_good`
- `dph_total`, `dph_base`, `dph_storage`, `min_bid`
- `storage_cost`, `disk_space_gb`, `geolocation`

`verified` と `rentable` は固定条件として常に適用するが、一覧表示からは除外する。

`offer_id` は検索時点の offer ID であり、レンタル済み instance ID ではない。実際のレンタルは、
一覧を確認した後に別途承認された create workflow で行う。

## Secret

Repository secret `VAST_API_KEY` だけを使用する。値はログへ出力しない。検索は Vast CLI の
`--api-key` へ渡し、read-only の offer search に限定する。

## 公式仕様との対応

- [Vast search offers API](https://docs.vast.ai/api-reference/search/search-offers)
- [Vast search offers CLI](https://docs.vast.ai/cli/reference/search-instances)
- [Vast CLI Hello World](https://docs.vast.ai/cli/hello-world)

CLI の `--raw`、`--type=bid|on-demand`、`--storage`、`--order`、`--limit` を使用する。
検索結果が空でも Action 自体は成功し、`inventory.md` に該当なしとして記録する。
