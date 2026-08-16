# ONNX Runtime Execution Provider

## 位置づけ

Execution Provider（EP）は、同じONNX artifactをどのbackendで実行するかを表します。NeMo/Transformersの違いとは独立した概念です。

```text
Target / Model
  ×
ONNX artifact
  ×
Execution Provider
```

現在の主要provider:

```text
CPUExecutionProvider
CUDAExecutionProvider
DmlExecutionProvider
CoreMLExecutionProvider
```

設定は`config/providers/`に置きます。

## CPU

用途:

- portable baseline
- cross-platform correctness
- hosted CIの基準
- 他EPとの比較基準

対応OS:

```text
Linux
Windows
macOS
```

CPUは最も安定した基準ですが、CPUで通ることはCUDA/DirectML/CoreMLで通ることを保証しません。

## CUDA

用途:

- NVIDIA GPU performance
- CUDA-specific compatibility
- production GPU benchmark

主な対象:

```text
Linux
Windows
```

CPU fallbackを許容する場合でも、fallback発生をrun metadataに残す必要があります。

## DirectML

Provider名:

```text
DmlExecutionProvider
```

主な対象:

```text
Windows
```

用途:

- Windows native GPU path
- vendor非依存のWindows GPU実行

標準GitHub hosted Windows runnerはDirectML GPU性能のauthoritative benchmark環境とはみなしません。

## CoreML

Provider名:

```text
CoreMLExecutionProvider
```

対象:

```text
macOS
```

本プロジェクトではONNX Runtime CoreML EPを使用します。MLXや`.mlpackage`をcanonical deployment artifactにはしません。

## Frameworkとの関係

providerはframework非依存です。

```text
Parakeet ONNX + CPU
Parakeet ONNX + CUDA
Parakeet ONNX + DirectML
Parakeet ONNX + CoreML

Whisper ONNX + CPU
Whisper ONNX + CUDA
Whisper ONNX + DirectML
Whisper ONNX + CoreML
```

ただし実際に特定EPで動くかどうかは、exportされたgraph、dynamic shape、operator support、runtime実装に依存します。

## Environmentとの違い

Provider:

> ORTのどのbackendを要求するか

Environment:

> どのOS・cache・resource policyで実行するか

したがって、たとえば`coreml.toml`と`macos.toml`は別責務です。

```text
config/providers/coreml.toml
config/environments/macos.toml
```

## CoreML parity

CoreML用には専用suiteを持ちます。

```text
config/evaluation/coreml-parity.toml
evaluation/manifests/coreml-parity.jsonl
```

想定する失敗分類:

```text
provider unavailable
session registration failure
graph shape incompatibility
graph compilation failure
runtime execution failure
unexpected CPU fallback
numerical parity failure
```

すべてを単一の「CoreML失敗」にまとめないことが重要です。

## Benchmark directory

Bucketではframework名ではなくenvironment/providerで分類します。

```text
benchmarks/<candidate-id>/
  linux-cpu/
  linux-cuda/
  windows-cpu/
  windows-cuda/
  windows-directml/
  macos-cpu/
  macos-coreml/
```

実際に実行していない組み合わせのdirectoryを事前に作る必要はありません。

## 比較条件

EP同士の性能・精度を比較するときは次を固定します。

```text
same candidate ID
same artifact SHA-256
same config version
same sample set
same decoder
same batch policy
```

比較する代表値:

```text
end-to-end RTF
ORT-only RTF
peak RAM / device memory
CER / WER
fallback有無
```

## 現在の制約

Target routingとrevision validationはframework-neutralですが、現在のPython/Rust ONNX evaluatorはCTC中心です。そのため、Whisper targetがCPU/CUDA/CoreML等を宣言していても、Whisper autoregressive runtimeが実装されるまでは同じ評価workflowを完全には実行できません。これはproviderの制約ではなくdecoder/runtime実装の制約です。