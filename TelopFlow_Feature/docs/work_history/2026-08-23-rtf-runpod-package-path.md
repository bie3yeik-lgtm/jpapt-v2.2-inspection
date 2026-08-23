# Work history: RunPod SSH package path failure

更新日: 2026-08-23

## 実runの観測

GHCR registry auth登録後、固定digestを使ったguarded RunPod smokeを1回実行した。

```text
run_id: rtf-runpod-local-20260823-r4-b1
pod: ms6m24bke6hu2x
gpu: rtx4090
image_digest: sha256:ed9843b177db3b6c7dfda261440a9996381e31e5e4726d5fb701d2f1ea6c1cdb
```

Pod作成、`RUNNING`への遷移、SSH command取得、SSH handshakeまでは成功した。
しかし、SSH経由でentrypointを実行した際に次のエラーで停止した。

```text
/opt/venv/bin/python: Error while finding module specification for 'benchmark_runner.load_fixture' (ModuleNotFoundError: No module named 'benchmark_runner')
```

content probe、metrics、result receiptは生成されなかった。adapterのcleanupにより
Podは実行終了後に削除され、実行後の孤児Podは残っていない。

## 原因判定

Python executable自体は`/opt/venv/bin/python`として解決できたが、RunPodが開始した
SSH sessionでは、Dockerfileの`PYTHONPATH`だけに依存したpackage discoveryが保証されない。
そのため、Python moduleの実体がimageに配置されていても、`benchmark_runner`をimport
できない経路が残っていた。

これはGHCR auth、Pod scheduling、SSH、NeMo推論、CUDA、fixture内容の失敗ではない。
失敗境界は「SSH sessionからPython packageを解決するimage runtime contract」である。

## 実装変更

`docker/rtf-benchmark/entrypoint.sh`で次を実行時に固定する。

1. `/opt/rtf-benchmark/benchmark-runner/benchmark_runner/__init__.py`の存在を検証する。
2. `/opt/rtf-benchmark/benchmark-runner`を`PYTHONPATH`の先頭へ明示的に追加する。
3. packageが欠落しているimageは推論開始前にfail-closedする。

`scripts/ci/test-rtf-provider-adapters.sh`には、この絶対package path、package存在検証、
`PYTHONPATH` exportを静的契約として追加した。

## 検証

```text
bash scripts/ci/test-rtf-provider-adapters.sh --mode static: PASS
bash -n docker/rtf-benchmark/entrypoint.sh scripts/run-benchmark.sh scripts/ci/test-rtf-provider-adapters.sh: PASS
git diff --check: PASS
```

static testはimage buildやprovider起動を行わないため、今回の修正を含む新digestの
実行証拠ではない。新しいGHCR digestが発行されるまでRunPodを再試行しない。

## 判定

- RunPod registry auth / private GHCR pull: verified
- Pod creation / runtime / SSH: verified
- Python package resolution: fixed in source, new image not yet published
- content probe / metrics / receipt: blocked pending new digest
- ranking: blocked

## 次の安全な作業

この変更をcommit、push、PR CIで検証し、mainへ取り込んだ後にGHCR build/publishと
RTF Resolverを連続実行する。Resolverが発行した新しいdigestだけを使い、同じ固定入力で
RunPod guarded batch 1を1回実行する。成功条件はfixture load、content probe、metrics、
receiptの全てが揃い、Podが削除済みであることとする。

