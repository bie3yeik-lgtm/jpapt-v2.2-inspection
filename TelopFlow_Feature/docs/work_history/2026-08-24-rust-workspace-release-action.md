# Rust Workspace Release Action 作成

## 目的

Rust workspace全体をGitHub Actionsでrelease compileし、実行ファイルbundleをartifactまたは
GitHub Releaseとして配布する入口を追加する。

## 変更

- `.github/workflows/rust-workspace-release.yml`
  - `rust-v*` tagとworkflow dispatchを受け付ける。
  - locked metadataを検証する。
  - `cargo build --locked --workspace --release --no-default-features --features cpu`を実行する。
  - binary bundleとSHA-256 checksumをuploadする。
  - release条件を満たす場合のみGitHub Releaseへ公開する。
- `docs/rust-workspace-release-action-20260824.md`
  - 実行手順、tag、artifact、責務境界を記録する。
- `docs/README.md`
  - release action文書への導線を追加する。

## 非対象

- CUDA/CoreMLのrelease binary追加
- model/audio/dataset artifactの配布
- 既存`rust-release.yml`のasr-eval配布仕様変更

## 検証

変更後にworkflow YAMLの静的構造、`git diff --check`、関連Rust packageのlocked build/testを
確認する。実GitHub Actionsのremote runとGitHub Release公開はworkflow dispatchまたはtag push
後に確認する。
