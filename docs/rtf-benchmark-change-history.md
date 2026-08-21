# RTF Benchmark 修正対応記録

最終更新: 2026-08-21

## 1. 目的と対象

本記録は、`nvidia/parakeet-tdt_ctc-0.6b-ja` の実GPU RTF benchmarkについて、これまでに行った設計変更、障害対応、結果保存、検証状態をまとめたものである。

対象となる実行経路は次のとおり。

```text
RTF Resolver
  -> 固定fixture生成・Hugging Face Dataset publish
  -> RTF Benchmark Run
       -> HF Jobs または RunPod Pod
       -> 共通GHCR image
       -> benchmark-runner
       -> HF Datasetへmetrics保存
  -> RTF Service Result Collection
       -> rtf-scores/へcommit・PR
```

Canonical benchmarkの入力は、次のrevision固定値を用いる。

- Model: `nvidia/parakeet-tdt_ctc-0.6b-ja`
- Model revision: `44edb27eea9317daf89333e75eb830db4b1cc298`
- Dataset: `japanese-asr/ja_asr.common_voice_8_0`
- Fixture repository: `gawohok7/rtf-benchmark-fixtures`
- Inspection profile: `smoke`
- Phase 1 GPU対象: T4、L4、A5000、RTX 3090、RTX 4090
- A100/H100: Phase 1対象外

## 2. 結果保存方針の変更

当初はGitHub Actions Artifactへの保存を中心にしていたが、Artifact生成完了待ちや後続Jobへの受け渡しが不安定で、ベンチマーク結果がリポジトリへ到達しない問題が発生した。

その後、次の方式へ整理した。

1. RTF Resolverが固定fixtureをHF Datasetへpublishする。
2. publish後のfixture commit SHAをreceipt/pointerへ記録する。
3. RTF Benchmark Runはfixture repository IDとimmutable revisionを入力として実行する。
4. provider側の実行結果はmetrics URI、result URI、SHA-256、job IDをreceiptとして返す。
5. RTF Service Result Collectionがreceiptを検証し、`rtf-scores/`へ結果をcommitしてPRを作成する。

最終結果の配置は次の形式である。

```text
rtf-scores/
  benchmark/
    benchmark-v1.fixture.json
    benchmark-v1.receipt.json
  smoke/
    {service}/{gpu}/
      batch-1/metrics.json
      batch-8/metrics.json
      batch-32/metrics.json
```

処理履歴とベンチマーク本体を混同しないため、結果JSONをbenchmark成果物として保存し、run summary/historyは別管理とした。

## 3. Resolverとfixture固定

### 3.1 固定fixtureの導入

毎回Common Voiceからランダムにサンプルを選ぶ方式では、結果の比較可能性が失われる。そのため、Resolverで以下を固定するようにした。

- dataset ID
- dataset commit SHA
- configuration/split
- resolver seed
- サンプル数の下限・上限
- 目標総音声時間
- 1サンプルの最大時間
- fixture manifest SHA-256
- fixture repository commit SHA

`smoke`の目標は、1サンプル30秒〜10分、20〜50本、総音声時間約1〜2時間である。現在のPhase 1では総時間の設定値を約1.5時間相当としている。

### 3.2 Resolver結果の自動引き渡し

Resolverの出力pointerとreceiptをBenchmark Runが読み取り、fixture revisionを手入力しない構成へ変更した。これにより、fixtureの生成結果と実推論が別revisionを参照する事故を防いだ。

関連commit例:

- `7001177` — revision-pinned HF fixture
- `85981fd` — fixture revisionの自動受け渡し
- `aaacfa5` — resolver pointerからfixture revisionを解決
- `334ccf7` — resolved benchmark manifestの追加

## 4. 共通Docker imageとimmutable入力

共通実行環境を`docker/rtf-benchmark/`へ集約した。Dockerfileには次のrepository linkageを付与している。

```dockerfile
LABEL org.opencontainers.image.source="https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection"
```

Benchmark RunはPackageの浮動tagではなく、GHCR packageのmanifest digestをActions内で毎回解決して使用する。Model revisionも固定値またはResolverから自動取得し、fixture revisionと同様にreceiptへ記録する。

対応した主な問題:

- GHCR `latest`やtagだけに依存する問題
- Package manifest取得のfallback不足
- Package検証の毎回実行による無駄
- HF flavorと選択GPUの不一致
- image pull完了前にbenchmarkを開始する問題

関連commit例:

- `296431a` — digest-pinned image
- `335d6d0` — image/model revision自動解決
- `97ad6b3` — provider package cacheとGHCR API解決
- `396fd65`, `4d857cf`, `bf9aae4` — GHCR digest解決fallback
- `478e3b6` — image準備待ち
- `77a7640` — Actions cache policy修正

## 5. HF Jobs実行

HF Jobsは`hf jobs run`から共通imageを起動し、credentialはRepository secretの`HF_TOKEN`を利用する。Dockerfileへtokenは書き込まない。

以前発生した問題:

- `service-id: hf-jobs`をrunnerが受け付けない契約不一致
- HF Jobsへ不要な`RTF_BATCH_SIZE=1`を渡していた
- selected GPUとHF flavorの不一致
- Model APIへ`revision`を誤った形式で渡していた
- `paths2audio_files`がNeMoの実際の`transcribe()`シグネチャに存在しなかった

対応後は、HF Jobs側も`RTF_SERVICE_ID=hf-jobs`として共通runnerを実行し、metricsをHF Datasetへpublishする。NeMoのAPI差異には、実際のimageに含まれるAPIに合わせた互換呼び出しを使用する。

関連commit例:

- `2ea984d` — HF hardware mapping
- `2af8744` — HF batch-size environmentの削除
- `0010776`, `16e6e65` — NeMo transcribe API互換化
- `aea5ed1` — precisionをmetricsへ追加

## 6. RunPod実行とPod lifecycle

RunPodでは、batchごとに次のライフサイクルを閉じる。

```text
Pod create
  -> image pull・SSH ready待機
  -> entrypointを明示実行
  -> metrics/receipt収集
  -> Pod delete
```

`--docker-args 'sleep infinity'`はコンテナを早期終了させないためのkeepaliveであり、SSH接続後にentrypointを明示的に起動する。Pod作成失敗時、SSH待機timeout時、metrics収集失敗時にもcleanupを行う。

対応した問題:

- Docker commandがENTRYPOINTへ単一文字列で渡る問題
- `sleep infinity`を認識せずcontainerが即終了する問題
- SSH port `22/tcp`が明示されていない問題
- Pod create直後にSSH readyと誤認する問題
- SSH待機timeoutが短く、image pull中にPodを破棄する問題
- create failure時にPodが残る問題
- nullのPod IDをdeleteしようとする問題
- termination deadlineの日時形式不一致

関連commit例:

- `c805441` — RunPod execution path
- `9e0fb72`, `f57287d` — SSH port公開
- `d86740a` — Pod lifecycle hardening
- `cf59a79` — readiness wait延長とfailure伝播
- `4985139`, `e88a10d` — keepalive引数互換
- `7ce00f8`, `47fae7d` — cleanup強化
- `b65f164`, `dee9e0a` — termination日時修正

## 7. 結果receiptと自動PR

provider実行後に、少なくとも次の値をreceiptへ保存する。

- `run_id`
- `job_id`
- `status`
- `result_repo_id`
- `result_revision`
- `result_uri`
- `result_sha256`
- `metrics_uri`
- `metrics_sha256`
- error code/message（失敗時）

metricsが生成されない場合は、成功扱いにせず`blocked`または`PROVIDER_EXECUTION_FAILED`として保存する。これにより、batch-1だけ成功しbatch-8/32が失敗した場合にも、欠落を成功結果として扱わない。

`rtf-service-result.yml`はreceiptからHF Dataset上のmetricsを取得し、対象branchへcommitしてPRを作成する。run summaryではなく、ベンチマーク本体の`metrics.json`を成果物として`rtf-scores/`へ保存する。

## 8. BatchサイズとOOM対応の経緯

### 8.1 実測されたOOM

L4で当初の`1/8/32`を実行した際、batch-1だけが完了し、batch-8/32はCUDA OOMになった。

代表的なログ:

- batch-8: 約20.44 GiB使用、空き約1.59 GiB、追加2.71 GiB要求
- batch-32: 約19.38 GiB使用、空き約2.65 GiB、追加3.56 GiB要求

この時点ではbatch定義を一時的に`1/2/4`へ変更した。しかし、ユーザー要求に合わせてbenchmark仕様は現在`1/8/32`へ復元している。

### 8.2 runnerのメモリ利用修正

OOMが単なるbatch間の解放漏れかを切り分けるため、次を実装した。

- ウォームアップを1サンプル・batch 1へ限定
- ウォームアップ結果を破棄
- `gc.collect()`を実行
- CUDA `empty_cache()`と`ipc_collect()`を実行
- 本計測前に`reset_peak_memory_stats()`を実行
- repeat間の一時結果を解放
- `float16`/`bfloat16`のautocastを本計測にも適用
- 文字列化後の`hypotheses`を破棄
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`をデフォルト設定

重要な発見として、元の実装ではautocastがウォームアップだけに適用され、本計測がautocast外で実行されていた。これは本計測時のメモリを不必要に増加させる不具合だった。

### 8.3 現在の解釈

batchごとはHF JobまたはRunPod Podが分離されるため、batch-1のGPUメモリがbatch-8へ持ち越される構造ではない。上記修正後も実GPUでbatch-8/32がOOMになる場合は、batchサイズと音声長による実ワーキングセット不足であり、解放漏れとは区別する必要がある。

現在のbatch契約は次のとおり。

```text
1 / 8 / 32
```

## 9. 主要な失敗と対応一覧

| 症状 | 原因 | 対応 |
|---|---|---|
| `rtf-scores/`に結果がない | Artifact依存と結果収集の非同期 | HF Dataset receipt経由のResult Collectionを導入 |
| fixture revisionが選択に載らない | Resolver出力とRun入力が手動分離 | pointer/receiptからSHAを自動引き渡し |
| `Model.from_pretrained(... revision=...)`失敗 | NeMoモデルAPIに誤ったkeywordを渡した | pinned snapshot download後に`.nemo`をrestore |
| `paths2audio_files`失敗 | NeMo `transcribe()` API不一致 | image内NeMo APIに対応する呼び出しへ変更 |
| `hf-jobs` invalid choice | CLI choicesとworkflow service IDの不一致 | service契約を統一 |
| HFへbatch=1が固定注入 | 不要な環境変数の残存 | HF batch環境変数を削除し、workflow loopで管理 |
| RunPodがすぐ終了 | keepalive commandの解釈不一致 | `sleep infinity`をentrypointとCLI双方で処理 |
| SSH timeout後にPod消失 | readiness待機・cleanup設計不足 | 30分待機、作成失敗cleanup、termination safetyを追加 |
| batch-8/32がmetricsなし | CUDA OOM | blocked receiptを保存し、成功扱いを禁止 |
| 本計測のメモリが過大 | autocastがウォームアップにしか適用されていなかった | 計測ループ全体をautocast内へ移動 |
| Image検証が毎回遅い | Package cache不足 | Actions cacheを導入・更新 |

## 10. 現在の検証状態

### 確認済み

- Python構文チェック
- Shell構文チェック
- JSON matrixのbatch定義
- `git diff --check`
- provider receiptのcontract tests
- GHCR digest、fixture revision、model revisionの入力経路の静的確認
- PR #322への最新変更反映

現在の最新commit:

```text
8fea9ce Restore benchmark batches and harden CUDA memory use
```

PR:

- [PR #322](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/pull/322)

### 未検証または実行環境依存

- 修正後Docker imageの再buildとGHCR publish
- 修正後imageによるHF Jobs実GPU実行
- 修正後imageによるRunPod実GPU実行
- L4でbatch-8/32が実際に完走するか
- 各GPUの実価格、peak VRAM、RTF、CER
- RunPodの全GPUでのSSH readinessと実推論

Mac上の静的検証成功は、HF Jobs/RunPodの実GPU完走を意味しない。実GPUで失敗した場合は、receiptのOOM情報、peak VRAM、実行batch、image digestを基に、解放漏れと実ワーキングセット不足を分離して判断する。

## 11. 今後の実行手順

1. PR #322をmergeする。
2. `docker/rtf-benchmark/`から共通imageを再buildし、GHCRへpublishする。
3. RTF Resolverを実行し、fixture commit SHAを確定する。
4. RTF Benchmark RunでproviderとGPUを選択する。
5. workflowがbatch `1/8/32`を順番に実行する。
6. HF Dataset上のmetrics URIとreceiptを確認する。
7. RTF Service Result Collectionが`rtf-scores/smoke/{service}/{gpu}/batch-{n}/metrics.json`へ保存したPRを確認する。
8. OOMの場合は成功扱いにせず、OOM発生位置とメモリ統計を記録する。
