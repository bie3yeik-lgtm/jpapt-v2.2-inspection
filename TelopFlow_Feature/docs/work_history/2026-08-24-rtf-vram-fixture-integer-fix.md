# RTF VRAM fixture integer overflow fix

## 目的

workspace全体テストを阻害していた、5,657,336,320 bytesのVRAM fixtureが
Rustのデフォルト`i32`整数として解釈される問題を解消する。

## 変更

`rust/crates/asr-contracts/tests/rtf_service.rs`のJSON fixtureリテラルに
`u64` suffixを付け、schemaの非負整数および実測VRAM値を保持した。
Production code、schema、metricsの単位は変更していない。

## 検証

- `cargo fmt --all -- --check`: PASS
- `cargo test --locked -p asr-contracts`: PASS（19 tests）
- `cargo test --locked --workspace`: PASS
- `git diff --check`: PASS

## 未確認事項

provider実行、HF Jobs、RunPod、GPU runtimeはこのfixture修正の対象外であり、
ローカルworkspaceテスト成功のみを受入れ根拠とする。
