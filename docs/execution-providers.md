# Execution Providers

provider policyの正本は `config/providers/*.toml` です。

```text
cpu.toml       CPUExecutionProvider
cuda.toml      CUDAExecutionProvider
directml.toml  DmlExecutionProvider
coreml.toml    CoreMLExecutionProvider
```

## 原則

providerはdecoder semanticsの正本ではありません。decoder/artifact requirementsはASR runtime catalog、evaluatorが実行可能かはevaluator capabilityで決定します。

```text
runtime profile requirements
  + candidate resolved contract
  + evaluator capability
  + provider/environment policy
  -> executable run
```

## Python ONNX

Python evaluatorはCPU/CUDA/DirectML/CoreMLを公開し、CTC/TDT/Whisper autoregressiveを扱います。

## Rust ONNX

Rust evaluatorはCPU/CUDA/DirectML/CoreMLをprovider capabilityとして公開しますが、decoder capabilityは現在CTCのみです。

## CoreML

CoreML固有のsession registration、graph shape、compilation、execution、provider fallbackはASR品質差と分離して扱います。CPUで動くことをCoreML成立の証拠にはしません。

## DirectML / CUDA

Windows DirectML、CUDAも同様にprovider availabilityと実executionを区別します。providerがインストール済みでもcandidate contract/evaluator capabilityが不適合なら実行しません。

## CI

Rust CIはLinux CPU、macOS CoreML、Windows DirectMLのbuild/unit経路を継続確認します。provider実機ASR parityはevaluation workflowの責務です。
