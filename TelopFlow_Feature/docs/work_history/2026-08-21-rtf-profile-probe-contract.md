# RTF profile / probe 規模契約の記録

## 目的

現行の `smoke` / `pref` labelと、ユーザーが指定した `smoke` / `pref` の意味を対応付け、
`probe`の実行規模を後続のResolver、Benchmark Run、ranking実装が参照できるようにした。

## 確認結果

- `smoke` は `smoke`、`pref` は `pref` として扱う。
- 既存metrics schema、receipt、保存pathは互換性のため直ちに改名しない。
- `probe`は総音声時間20〜50時間、サンプル数100〜300本、短尺から1時間超を混在させる。
- `probe`は `smoke` / `pref`の別名ではない。

## 変更

- `docs/rtf-profile-and-probe-contract-20260821.md`を追加した。
- `docs/README.md`から正本文書へリンクした。

## Evidence

### Source/static

- `evaluation/schemas/rtf-service-metrics.schema.json`でlegacy profileが`smoke|pref`であることを確認。
- `scripts/ci/build-rtf-benchmark-record.py`でprofile入力が`smoke|pref`であることを確認。
- `evaluation/manifests/rtf-phase1.jsonl`で現行manifestが`smoke`を使用していることを確認。

### 未検証

- 実probe manifestの総音声時間、長尺サンプル混在、サンプル数。
- HF Jobs / RunPodでのprobe実行結果。
- legacy labelをschema version付きで移行する実装。

## Blocker / 次の安全な作業

実音声のmaterialized manifestがないため、probeの規模契約は文書上の正本化までとする。
次はResolverが生成したmanifestを対象に、Rust側でprofileとduration/count分布を検証する契約テストを
追加する。ローカルGPU smokeは実施しない。
