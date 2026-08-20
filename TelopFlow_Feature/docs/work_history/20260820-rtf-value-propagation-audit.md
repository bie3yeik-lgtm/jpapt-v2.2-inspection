# RTF値受け渡し監査・修正

## 目的

Resolverで確定したRTF benchmarkの値が、HF Jobs/RunPod、Docker runner、結果収集へ同じ値で渡ることを保証する。

## 変更

- provider adapterからprofile、dataset条件、repeat、fixture manifest SHAをDockerへ伝播。
- RunPod Pod IDを`RTF_JOB_ID`としてreceiptへ伝播。
- publisherのpayload初期化順序とrun ID検証を修正。
- fixture manifest SHA、audio SHA、順序、重複ファイル名を検証。
- metricsとbenchmark recordへfixture repository/revision/profileを追加。
- result/metrics URIとSHA、service collection入力の一致検証を追加。
- 手動dispatch helperへprofile、GPU、batch sizeを追加。

## 検証

- `cargo test --locked -p asr-contracts --test rtf_service`: 5 tests passed
- `bash -n`で関連Shellを検証
- `python -m py_compile`で関連Pythonを検証
- `actionlint`で関連workflowを検証
- `git diff --check`: passed

## 未検証・次の作業

HF Jobs/RunPodの実GPU実行、HF Datasetへの実upload、provider実行証拠は資格情報とGPUが必要なため未検証。
次はrepository全体のcheckと変更差分確認を行う。
