# RTF profile label と probe 規模契約

更新日: 2026-08-21
状態: `smoke` / `pref` / `probe` を使用する現行正本

## 1. Profile label

RTFのprofileは次の3値だけを使用する。

| profile | 目的 | 規模 |
|---|---|---|
| `smoke` | 0〜100 users向けの初期サービス選定 | 20〜50本、総音声約1.5時間、30秒〜10分を目安 |
| `pref` | 比較候補の優先実行 | 50〜150本、総音声5〜10時間を目安 |
| `probe` | 大規模なprovider/dataset実行可能性確認 | 20〜50時間、100〜300本、短尺〜1時間超を混在 |

過去のprofile表記はactive contractから撤去する。既存成果物を参照する必要がある場合も、
新しいrecord、保存path、workflow inputには過去表記を再導入しない。

## 2. Probeの厳格な条件

`probe`は`smoke`や`pref`の別名ではない。manifestのmaterialized audio durationから、次を
実測して検証する。

- 総音声時間: 72,000〜180,000秒
- サンプル数: 100〜300本
- 少なくとも1本は3,600秒以上
- 少なくとも1本は3,600秒未満

条件を満たさないmanifestはprovider実行へ進めず、resolverで拒否する。dataset metadataの
推定値やprofile labelだけではprobe成立としない。

## 3. Workflow境界

- `RTF Resolver`: `smoke` / `pref` / `probe`を選択できる。
- `RTF Benchmark Run`: 現段階ではHF Jobs / RunPodの`smoke`実行に限定する。
- `RTF Service Result Collection`: 3 profileを受領し、保存pathにも同じ値を使う。
- `benchmark-ranking`: 3 profileを指定できるが、異なるprofileのrecordを同一ランキングへ混在させない。

`smoke`の外部実測がこの作業の優先受入であり、ローカルGPU smokeは受入条件に含めない。

## 4. Identity

`inspection_profile`、manifest、保存path、branch名、ranking inputは同じprofile値を使用する。
profile変換によってmetrics、run identity、manifest SHA-256、result/metrics SHA-256を変更しない。

```text
rtf-scores/<smoke|pref|probe>/<service_id>/<gpu>/batch-<batch>/
```

profileが異なるrecordは、同じmodel、GPU、batchであっても比較対象を分離する。`probe`の
長時間結果を0〜100 users向けsmokeのrankingへ流用しない。

## 5. 受入条件

- source-controlled schema、CLI、workflow inputが`smoke|pref|probe`だけを受け付ける。
- 過去のprofile表記のactive RTF参照が残っていない。
- smokeはHF/RunPodで実行し、local GPU実行を要求しない。
- probeはduration、count、短尺/長尺混在をmanifest実体から検証する。
- profile不一致、manifest不足、provider結果欠落はfail-closedになる。
