# Execution Providers

DirectML is retired. It is not an active provider, configuration, runtime
feature, strict probe, candidate evaluation, or acceptance route. The
DirectML sections below are retained only as historical audit notes and must
not be used to schedule work.

## 1. 共通原則

Execution Providerの評価では次の状態を分離します。

```text
compiled
  ↓
registered
  ↓
session_created
  ↓
execution_proven
  ↓
assignment_proven
```

途中まで成功しても後段の証明にはなりません。特に「providerを登録できた」「inferenceが成功した」「acceleratorへnodeが割り当てられた」は別の事実です。

## 2. Providerと現行CI

| provider | 主OS | Rust CI | strict readiness | production/reference evaluation |
|---|---|---|---|---|
| CPU | Linux/Windows/macOS | 3 OS | 不要 | CPU Full / Cross Platform / Rust Eval |
| CUDA | Linux | 標準Rust CI matrix外 | 現行専用probeなし | config/runtime capabilityとして保持 |
| CoreML | macOS | `macos-coreml` | Provider Strict Probes | Cross Platform / Rust Eval |

`rust-ci.yml` はcompile/check/clippy/unit validationです。real accelerator proofは `provider-strict-probes.yml` や実評価で行います。

## 3. CPU

CPUはreference execution providerとして最も直接的です。

```text
CPUExecutionProvider
```

CPU runでも比較再現性のため、run-contextへ次を固定します。

- OS / architecture
- ORT version
- runtime implementation
- thread/session configuration
- optimization level
- candidate/config/dataset identity

## 4. CUDA

CUDAではregistrationだけでなくdynamic library/runtime compatibilityを確認します。

代表的failure:

- CUDA runtime mismatch
- cuDNN mismatch
- cuBLAS loader failure
- ORT/CUDA major incompatibility
- CPU fallbackによる見かけ上の成功

数値差はprovider failureと混同せず、CER/WER、token parity、numeric parityを別指標にします。

現行standard Rust CI matrixにはCUDA jobはありません。CUDA対応を変更した場合は、Linux GPUを備えた実環境で別途execution proofが必要です。

## 5. DirectML (historical audit only)

DirectMLのhard session constraints:

```text
execution_mode = sequential
enable_mem_pattern = false
```

同じInferenceSessionへのconcurrent Runを前提にしません。

DirectMLはWindows環境で評価します。HF JobsはLinux computeなのでDirectML execution proofの代替にはなりません。

### CIレベル

`rust-ci.yml`:

```text
windows-latest
features = cpu,directml
cargo check / clippy / test
```

これはDirectML featureを含むworkspaceがbuild/test可能であることの確認です。

### Strict readiness

`provider-strict-probes.yml`:

```text
windows-latest
synthetic CTC candidate
strict DirectML evaluator
stdout/stderr/exit code/resultsを保存
Rust asr-provider-readinessで分類
```

measurement stepは `continue-on-error` ですが、failureを握り潰すためではありません。後段classifierへfailure evidenceを渡すためです。

### Production Rust evaluation

`rust-eval.yml` の `windows-directml` matrixで実candidateを評価します。default inputでは `strict_provider=true` なのでCPU fallbackなしproof runになります。

## 6. CoreML

CoreMLはmacOS / Apple Siliconを主対象にします。

failure categoryを分離します。

```text
provider unavailable
session registration failure
graph shape incompatibility
graph compilation failure
runtime inference failure
zero-dimension tensor
numeric/parity failure
```

「dynamic shapeを持つ」ことと「runtimeでzero dimensionが出る」ことは同じfailureではありません。

### CIレベル

`rust-ci.yml`:

```text
macos-15
features = cpu,coreml
cargo check / clippy / test
```

### Strict readiness

`provider-strict-probes.yml`:

```text
macos-14
synthetic CTC candidate
strict CoreML runtime probe
Rust readiness classification
```

### Production/reference evaluation

```text
Cross Platform ONNX Parity -> macOS CoreML / Python evaluator
Rust Cross Platform Evaluation -> macOS CoreML / Rust CTC evaluator
```

## 7. ORT optimization level

Rust evaluationではworkflow input/CLIで明示できます。

```text
configured
disable
basic
extended
all
```

`rust-eval.yml` のdefaultは `configured` です。

optimizer canaryでは最低限次を比較します。

```text
ORT_DISABLE_ALL
ORT_ENABLE_BASIC
ORT_ENABLE_EXTENDED
ORT_ENABLE_ALL
```

optimization levelを変更したrunはrun-contextへ記録し、異なるexecution conditionとして扱います。

## 8. Strict provider mode

Rust run-context builderへ `--strict-provider` を指定すると、non-CPU providerでCPU fallbackを禁止するproof runを構築します。

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  build-run-context \
  ... \
  --provider directml \
  --strict-provider
```

strict modeでsuccessful inferenceが得られればprovider execution evidenceは強くなりますが、node assignment APIで直接計測していなければ `assignment_proven` とは限りません。

## 9. Tensor sanity

providerに依存せずruntime boundaryで拒否する代表条件:

- empty waveform
- non-finite waveform
- zero-sized output dimension
- NaN / Inf logits
- decoder state shape/dtype mismatch
- Whisper cache transition mismatch
- TDT token/duration logits dimension mismatch

accelerator固有failureを「認識精度低下」として後段へ流さないためです。

## 10. Rust provider features

Rustのprovider supportはcompile-time featureです。

代表例:

```text
cpu
cpu,directml
cpu,coreml
```

runtimeでprovider名を指定しても、binaryにfeatureがなければcompiled=falseとしてfailします。

provider supportとdecoder supportは別です。Rust evaluatorは現在CTCのみなので、CoreML/DirectML featureが有効でもRust TDT/Whisperが使用可能になるわけではありません。

## 11. Provider telemetry

観測した値だけをresultへ記録します。

```json
{
  "requested": "directml",
  "registered": true,
  "execution_proven": true,
  "fallback_detected": false,
  "fallback_only": false,
  "assigned_nodes": null,
  "fallback_nodes": null
}
```

未計測値を0へ置き換えません。

## 12. GitHub Actionsの選び方

| 確認したいこと | workflow |
|---|---|
| provider featureを含めてcompile/testできるか | Rust CI |
| DirectML/CoreMLでstrict runtimeが成立するか | Provider Strict Probes |
| Python ONNXのmacOS CoreML parity | Cross Platform ONNX Parity |
| Rust CTCをDirectML/CoreMLで実candidate評価 | Rust Cross Platform Evaluation |
| production release gate用CPU品質 | CPU Full Evaluation |

各workflowの詳細は [github-actions.md](./github-actions.md) を参照してください。
