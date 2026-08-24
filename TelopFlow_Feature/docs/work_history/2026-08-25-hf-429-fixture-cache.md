# Hugging Face 429待機とfixture重複取得の解消

## 目的

RunPod benchmarkで、各batchの新しいPodが同一revisionのfixtureと音声をHugging Face Hubから取得し、5分windowの429制限に到達した問題を解消する。

## 実装

- `scripts/ci/prepare-rtf-fixture.py`
  - Runner上でfixture manifestと音声を一度だけ取得する。
  - fixture manifest SHA-256と各音声SHA-256を検証する。
  - Hubの429時は300秒待機して再試行する。
- `.github/workflows/rtf-benchmark-run.yml`
  - provider実行前にRunner側でfixtureをmaterializeする。
  - materialized fixtureをsmoke専用派生Docker imageへ格納し、digest固定でpushする。
  - `.ci/rtf-fixture`はimage build完了後に破棄される一時生成物でありcommitしない。
- `docker/rtf-benchmark-smoke/Dockerfile`
  - 既存のdigest-pinned benchmark imageをbaseにし、検証済みfixtureを内蔵する。
- `scripts/run-benchmark.sh`
  - 旧来の明示local fixture転送経路を互換用に保持するが、canonical smoke workflowでは使用しない。
- `docker/rtf-benchmark/entrypoint.sh`
  - `RTF_FIXTURE_LOCAL_DIR`がある場合はHubへアクセスせずlocal fixture loaderを使用する。
- `docker/rtf-benchmark/benchmark-runner/benchmark_runner/load_fixture.py`
  - local fixture入力を追加した。
  - 直接Hub取得経路にも429時300秒待機・最大3回のbounded retryを追加した。
- `.github/workflows/rtf-benchmark-contracts.yml`
  - 5分429待機、Runner materialization、Pod転送、local loaderを静的契約化した。

## 期待される動作

```text
Runner: Hubからfixtureを1回取得・SHA検証
  -> smoke fixture imageへ格納・digest固定push
  -> batch 1/8/32 Pod: 同じfixture内蔵imageを使用、Hubアクセスなし
```

直接Hub取得が残る経路では、429を即時失敗にせず300秒待機して再試行する。

## 検証

- Bash syntax: PASS
- Python compile: PASS
- 対象workflow YAML parse: PASS
- `bash scripts/ci/test-rtf-provider-adapters.sh --mode static`: PASS
- `git diff --check`: PASS

## 未検証

実RunPodでのfixture転送と次回Actions実行は未検証。次回はログに以下が出ることを確認する。

- `Build and publish smoke fixture image`
- Pod内でのHub `HEAD`アクセスが発生しないこと
- `RTF_BUNDLED_FIXTURE_DIR`経路でcontent probeが完了すること

## 追補: Actions run 32761735646

このrunはRunPodの起動前、GHCRのbenchmark image build中に失敗した。`huggingface_hub==1.24.0`では
`HfHubHTTPError`をトップレベルからimportできないため、fixture loaderとRunner側のmaterializerを
`huggingface_hub.utils`からimportするよう修正した。したがって、このrunではPodの生存時間や429待機の
動作までは到達していない。
