# ONNX Runtime Execution Provider

## 位置づけ

Execution Provider（EP）は、同じONNX artifactをどのbackendで実行するかを表します。NeMo/Transformersの違い、decoder実装、evaluator capabilityとは独立した概念です。

```text
Target / Model
  ×
Evaluator capability
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

CPUで通ることはCUDA/DirectML/CoreMLで通ることを保証しません。

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

CPU fallbackを許容する場合でも、fallback発生をrun metadataに残します。

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
Parakeet ONNX + CPU/CUDA/DirectML/CoreML
Whisper ONNX  + CPU/CUDA/DirectML/CoreML
```

ただし実際に実行可能かどうかは、少なくとも次の3条件が独立して成立する必要があります。

```text
1. evaluatorがdecoder/runtimeを実装している
2. ONNX graphが対象EPでsession化できる
3. 実行時operator/shape/fallback条件を満たす
```

## Evaluator capabilityとの違い

Evaluator capabilityは「その実装がどのdecoderを処理できるか」です。

```text
config/evaluators/python-onnx.toml
config/evaluators/rust-onnx.toml
```

Provider capabilityは「そのONNX graphをどのORT backendで実行できるか」です。

したがってWhisper targetについて:

```text
CoreML EPでgraphが実行可能
```

であっても、Whisper autoregressive evaluatorが未実装ならend-to-end評価は実行できません。逆にdecoder runtimeが実装済みでも、CoreML graph compilationに失敗すればCoreML runは成立しません。

## Environmentとの違い

Provider:

> ORTのどのbackendを要求するか

Environment:

> どのOS・cache・resource policyで実行するか

```text
config/providers/coreml.toml
config/environments/macos.toml
```

は別責務です。

## CoreML parity

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

すべてを単一の「CoreML失敗」にまとめません。

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

実行していない組み合わせのdirectoryを事前に作る必要はありません。

## 比較条件

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

Target routingとrevision validationはframework-neutralです。一方、現在の`python-onnx` / `rust-onnx` evaluator capabilityはCTCのみです。

この制約はprovider定義へ書かず、`config/evaluators/*.toml`へ保持します。TDT/Whisper runtime追加時もprovider configやworkflowへdecoder固有条件を追加しません。

関連文書:

```text
docs/multi-framework-asr.md
docs/evaluation.md
docs/github-actions.md
```
