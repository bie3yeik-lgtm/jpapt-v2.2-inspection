# RunPod smoke runtime initialization evidence

更新日: 2026-08-23

## 目的と範囲

GHCR publish後に生成された新しいRTF benchmark imageを使い、RunPod
RTX4090のguarded smokeを1回だけ起動して、前回修正したSSH環境転送とPython
interpreter解決の前にPod runtimeが到達するかを確認した。失敗時のprovider状態を
推測せず保存できるよう、RunPod診断artifactの収集経路も追加した。

## 固定した入力

```text
image: ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@sha256:ed9843b177db3b6c7dfda261440a9996381e31e5e4726d5fb701d2f1ea6c1cdb
model: nvidia/parakeet-tdt_ctc-0.6b-ja
model_revision: 44edb27eea9317daf89333e75eb830db4b1cc298
dataset: japanese-asr/ja_asr.common_voice_8_0
dataset_revision: bf8819e8d9a5feb51b0c718686bd20ea67a3c729
fixture_repo: gawohok7/rtf-benchmark-fixtures
fixture_revision: 0556991b56c5f6e9753402ab2265232ce2577ae1
manifest_sha256: 9c47976f6101ebca1fc2575d46fde80d9a33dbc14b1e1f6dc2ca9aeb57a87694
profile: smoke
gpu: rtx4090
batch_size: 1
```

## 外部実run結果

GHCR workflow `32621565092` は成功し、publish後のRTF Resolverも成功した。
Resolverはfixtureを更新し、上記のrevisionとmanifest SHAを生成した。

RunPod local guarded run `rtf-runpod-local-20260823-r3-b1` ではPod
`jgvt0ox3ryi73p`の作成まで成功した。しかし約10分間、次の状態から進まなかった。

```text
desiredStatus=RUNNING
runtimeAvailable=false
runtimeStatus=initializing
SSH probe: not started
benchmark entrypoint: not started
content probe: not started
metrics: not produced
```

費用を抑えるためreadiness待機を中断し、EXIT cleanupでPodを削除した。実行後の
RunPod Pod一覧は空である。このrunはCUDA、Python、fixture、metrics処理の失敗では
なく、providerのruntime/image initialization未完了として扱う。

追加のread-only確認で、RunPod accountのregistry auth一覧には既存のNVIDIA registry
credentialだけがあり、GHCR用credential IDは存在しなかった。GHCR packageがprivate
visibilityの場合、Pod createへ`--registry-auth-id`を渡さない限りimage pullが完了
しない可能性がある。このためadapterは`RUNPOD_REGISTRY_AUTH_ID`を任意で渡せる一方、
GitHub Actionsのprivate-GHCR laneでは`RTF_RUNPOD_REQUIRE_REGISTRY_AUTH=1`により
ID未設定のPod作成を事前停止する。

## 実装した診断境界

`scripts/run-benchmark.sh` に `RTF_LOCAL_PROVIDER_DIAGNOSTICS` を追加した。
RunPodの次の状態を、秘密値を含めずJSON artifactへ保存する。

- phase: `pod_create` / `readiness_poll` / `readiness_failed` / `benchmark_execution`
- Pod ID、GPU、image digest、run ID
- `pod get`、`pod list`、`ssh info`のraw response
- SSH diagnostic、typed error code、観測時刻

`.github/workflows/rtf-benchmark-run.yml` は各batchの
`results/batches/batch-*/provider-diagnostics.json`を既存result artifactに含める。
これによりruntime初期化停滞、SSH endpoint未公開、Pod終了をreceiptとは別の
provider evidenceとして確認できる。

RunPod createには、設定時のみ`--registry-auth-id "$RUNPOD_REGISTRY_AUTH_ID"`を追加
する。credential passwordそのものはPod metadataへ渡さない。

## 検証結果

```text
bash -n scripts/run-benchmark.sh scripts/ci/test-rtf-provider-adapters.sh: PASS
bash scripts/ci/test-rtf-provider-adapters.sh --mode static: PASS
bash scripts/ci/test-rtf-provider-adapters.sh --mode mock: PASS
git diff --check: PASS
```

mockではRunPod診断artifactについて次を検証した。

```text
schema_version=1
phase=benchmark_execution
pod_id=runpod-mock-pod
```

これはRunPod実runtimeの成功証拠ではない。RunPod本番metrics、content probe、
SSH経由entrypoint実行は未検証のままである。

## 判定と次の安全な作業

- GHCR publish: verified
- RTF Resolver/fixture: verified
- RunPod Pod create: verified
- RunPod runtime initialization: blocked/not verified
- RunPod SSH execution: not reached
- RunPod content/metrics/result receipt: not produced
- Ranking投入: blocked

次回のguarded試験では同じ固定入力を使い、診断artifactを必ず保存する。runtimeが
初期化完了しない場合は、同一imageの再試行を繰り返さず、RunPod側のimage pull、
registry visibility/auth、GPU pool状態を外部サービスの状態として確認する。

## ロールバック

`RTF_LOCAL_PROVIDER_DIAGNOSTICS`を未設定にすれば診断artifact出力だけを無効化できる。
既存receipt、metrics、fixture、Podを変更・再利用しない。
