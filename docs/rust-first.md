# Rust-first Runtime

Rustはproduction-oriented ONNX evaluator/runtimeとして扱います。ただし、実装能力は文書で先行宣言せず `config/evaluators/rust-onnx.toml` のcapabilityを正本とします。

## 現在の公開capability

```text
implementation          rust
backend                 onnxruntime
supported decoder       ctc
supported providers     cpu / cuda / directml / coreml
artifact contract       ctc-single-graph-v0 / v1
```

TDT/WhisperはPython側にruntime実装がありますが、Rust evaluatorでは現在公開していません。

## CTC path

Rust evaluatorはresolved config/candidate contractを受け取り、ONNX Runtime providerを構成してCTC inference/evaluationを行います。candidate metadataからdecoder semanticsを再解釈しません。

## Provider

provider availabilityと実executionを区別します。CPU/CUDA/DirectML/CoreMLのprovider差分はconfig/provider layerへ閉じ込め、candidate schemaを分岐しません。

## CI

`.github/workflows/rust-ci.yml` は少なくとも次を確認します。

```text
rustfmt advisory
linux-cpu       cargo check + unit tests
macos-coreml    cargo check + unit tests
windows-directml cargo check + unit tests
```

release artifact生成は `rust-release.yml` の責務です。

## Decoder拡張時

TDT/WhisperをRustへ追加する場合は、先にruntime/evaluator実装とtestを成立させ、その後 `config/evaluators/rust-onnx.toml` のcapabilityを開放します。capabilityだけを先行してtrueにしません。
