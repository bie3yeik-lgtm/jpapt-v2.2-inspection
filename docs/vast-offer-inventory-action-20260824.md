# Vast offer inventory GitHub Action

## 目的

`.github/workflows/vast-offer-inventory.yml`は、親リポジトリのAudioAttention/Vast方針にある
デフォルト条件で、現在レンタル可能なVast offerを検索する読み取り専用workflowである。
instanceの作成・停止・破棄は行わない。

## デフォルト条件

初期値は`profile=student`、`pricing_type=bid`である。

### Student

```text
gpu_name in [RTX_4090, RTX_3090]
num_gpus=1
reliability>0.98
verified=true
rentable=true
storage=100 GiB
pricing_type=bid (interruptible)
order=dph_total ascending
```

### Teacher

```text
gpu_ram>=48000 MiB
num_gpus=1
reliability>0.98
verified=true
rentable=true
direct_port_count>=1
storage=150 GiB
order=dph_total ascending
```

Teacherは`profile=teacher`を選び、通常は`pricing_type=on-demand`を指定する。
`profile=all`ではStudentとTeacherを同時に検索する。

## 出力

Actions artifact `vast-offers-<run_id>`に次を保存する。

```text
vast-cli-version.txt
vast-offers/student-<pricing>.json
vast-offers/teacher-<pricing>.json
vast-offers/inventory.json
vast-offers/inventory.csv
vast-offers/inventory.md
```

一覧には次を含める。

- offer/instance作成に使う`offer_id`
- `machine_id`, `gpu_name`, `gpu_ram_gb`, `num_gpus`
- `reliability`, `verified`, `rentable`, `direct_port_count`
- `cuda_max_good`
- `dph_total`, `dph_base`, `dph_storage`, `min_bid`
- `storage_cost`, `disk_space_gb`, `geolocation`

`offer_id`は検索時点のoffer IDであり、レンタル済みinstance IDではない。実際のレンタルは、
一覧を確認した後に別途承認されたcreate workflowで行う。

## Secret

Repository secret `VAST_API_KEY`だけを使用する。値はログへ出力しない。検索はVast CLIの
`--api-key`へ渡し、read-onlyのoffer searchに限定する。

## 公式仕様との対応

- [Vast search offers API](https://docs.vast.ai/api-reference/search/search-offers)
- [Vast search offers CLI](https://docs.vast.ai/cli/reference/search-instances)
- [Vast CLI Hello World](https://docs.vast.ai/cli/hello-world)

CLIの`--raw`、`--type=bid|on-demand`、`--storage`、`--order`、`--limit`を使用する。
検索結果が空でもAction自体は成功し、`inventory.md`に該当なしとして記録する。
