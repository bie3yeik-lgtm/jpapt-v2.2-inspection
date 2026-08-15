# ONNX Runtime Execution Providers

## Purpose

Execution Providers (EPs) describe where and how ONNX Runtime executes the
same deployment model.

The project currently models:

```text
CPUExecutionProvider
CUDAExecutionProvider
DmlExecutionProvider
CoreMLExecutionProvider
```

Provider configuration lives under:

```text
config/providers/
├── cpu.toml
├── cuda.toml
├── directml.toml
└── coreml.toml
```

Provider configuration must not be mixed into model configuration.

## CPU

Configuration:

```text
config/providers/cpu.toml
```

Role:

- canonical portable ONNX baseline
- cross-platform correctness
- hosted CI baseline
- fallback reference for other EPs

Platforms:

- Linux
- Windows
- macOS

CPU is the primary baseline because it is available on all supported systems
and avoids hardware-specific graph partitioning.

## CUDA

Configuration:

```text
config/providers/cuda.toml
```

Platforms:

- Linux
- Windows

Role:

- GPU performance
- CUDA-specific compatibility
- deployment benchmarking

CPU fallback may be enabled, but fallback must be reported.

A session that includes CUDA in the provider list does not prove the complete
graph executed on CUDA.

## DirectML

Configuration:

```text
config/providers/directml.toml
```

Platform:

```text
Windows
```

Provider name:

```text
DmlExecutionProvider
```

Role:

- native Windows GPU execution
- hardware-agnostic Windows GPU path

Standard hosted Windows GitHub runners are not considered authoritative
DirectML GPU performance machines.

Hosted Windows tests may still verify configuration or CPU behavior.

## CoreML

Configuration:

```text
config/providers/coreml.toml
```

Platform:

```text
macOS
```

Provider name:

```text
CoreMLExecutionProvider
```

The project uses ONNX Runtime CoreML EP only.

It does not use:

- MLX
- native `.mlpackage` deployment as the project runtime
- separate Core ML model conversion as the canonical artifact

The canonical deployment artifact remains ONNX.

## CoreML parity

The dedicated manifest:

```text
evaluation/manifests/coreml-parity.jsonl
```

contains duration bands intended to expose shape/compile/provider boundary
issues.

CoreML failures should be classified separately where possible, for example:

```text
provider unavailable
session registration failure
graph shape incompatibility
graph compilation failure
runtime execution failure
unexpected CPU fallback
numerical parity failure
```

Do not collapse all of these into a generic "CoreML failed".

## Provider vs environment

Provider answers:

> Which ORT backend should execute the graph?

Environment answers:

> What operating system, cache, resource, and concurrency policy applies?

Therefore:

```text
config/providers/coreml.toml
```

is distinct from:

```text
config/environments/macos.toml
```

Likewise CUDA configuration is not inherently a Windows or Linux environment
definition.

## Provider fallback

When CPU fallback is permitted, results must distinguish:

```text
requested provider
available providers
actual graph assignment
fallback occurrence
```

Fallback can make a run appear successful while invalidating the intended
performance measurement.

## Performance authority

### Hosted Ubuntu

Suitable for:

- CPU canonical full evaluation
- general Linux correctness

Not automatically authoritative for a user's deployment GPU.

### Hosted Windows

Suitable for:

- native Windows correctness
- CPU checks

Not authoritative DirectML GPU benchmarking by default.

### Hosted macOS

Suitable for:

- CPU/CoreML compatibility and parity

Not authoritative performance for a specific local Apple Silicon machine.

### Local Apple Silicon

Suitable for:

- machine-specific CPU/CoreML comparison
- authoritative local performance measurements

The result's host identity must remain part of benchmark provenance.

## Configuration checks

Before evaluation the resolver should verify:

1. the model declares the provider as supported
2. the environment maps to that provider
3. the provider supports the current OS
4. the requested evaluation suite supports the environment
5. the ONNX Runtime installation actually exposes the provider

## ORT session layer

Expected Python location:

```text
python/src/parakeet_onnx/runtime/
├── session.py
├── providers.py
└── tensors.py
```

Expected Rust location:

```text
rust/crates/asr-runtime/
```

Both implementations should expose equivalent logical provider identities even
when provider-option APIs differ.

## Benchmark comparison

When comparing EPs, keep constant:

```text
same ONNX artifact
same artifact SHA-256
same sample set
same decoder
same batch size
same evaluation revision
```

Then compare:

```text
end-to-end RTF
ORT-only RTF
memory
quality
fallback
```

Otherwise the provider comparison is confounded by different model or
evaluation inputs.
