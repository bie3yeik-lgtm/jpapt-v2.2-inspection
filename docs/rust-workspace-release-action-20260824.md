# Rust Workspace Release Action

## 目的

`.github/workflows/rust-workspace-release.yml`は、repository rootのCargo workspaceに含まれる
Rust targetをLinuxのrelease profileでコンパイルし、生成された実行ファイル群をtar.gzとSHA-256
checksumとしてGitHub Actions artifactへ保存する。タグまたは明示的なworkflow dispatchでは、同じ
artifactをGitHub Releaseへ添付する。

## 実行方法

### buildだけ行う

Actions UIで`Rust Workspace Release`をworkflow dispatchし、`create_release=false`を指定する。

### GitHub Releaseを作る

次のタグをpushする。

```text
rust-v0.1.0
```

またはworkflow dispatchで`create_release=true`とし、`tag=rust-v0.1.0`を指定する。

既存の`rust-release.yml`が使用する`v*`タグとは分離している。既存workflowは`asr-eval`のOS別
配布、今回のworkflowはworkspace全体のLinux binary bundleを担当する。

## Build contract

```text
cargo metadata --locked --no-deps --format-version 1
cargo build --locked --workspace --release --no-default-features --features cpu
```

- `Cargo.lock`を必須とし、依存解決の再現性を維持する。
- Rust workspaceの全packageをrelease buildする。
- canonical runtimeの現行CIと同じ`cpu` feature境界を使用する。
- model、audio、dataset、onnx、nemoなどの大容量artifactはReleaseへ含めない。
- GitHub Actions cacheはCargo registry/git、ORT cache、`target`のみを対象とする。

## Artifact contract

生成物は次の形式である。

```text
rust-workspace-<github-sha>.tar.gz
rust-workspace-<github-sha>.sha256
```

tar.gz内部には、release binaryを格納する`bin/`と、含まれるbinary名を列挙した
`RELEASE_BINARIES.txt`を含める。checksumはRelease asset自身のSHA-256である。

## Scope and limitations

- 現行workflowはLinux `ubuntu-latest`のCPU feature buildである。
- CUDA/CoreMLのplatform releaseは既存の`rust-release.yml`およびRust CIの責務であり、今回の
  workflowでは混在させない。
- GitHub Releaseへの公開は`rust-v*`タグまたは明示dispatch時だけ行う。
- Actions artifactの保存だけならRelease tagは不要である。

## Acceptance evidence

- locked metadata validation成功
- workspace release build成功
- release binaryが一つ以上生成されること
- tar.gzとchecksumがartifactへuploadされること
- release modeではtag prefixが`rust-v`であること
