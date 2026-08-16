# Execution Providers

## 1. 共通原則

Execution Providerの評価では、availability・registration・session creation・successful inference・node assignmentを同一視しません。

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

途中まで成功しても、その後段の証明にはなりません。

## 2. CPU

CPUはreference execution providerとして最も直接的に扱えます。

- `CPUExecutionProvider`
- fallback概念が実質的に不要
- execution成功をprovider使用の強い証拠として扱える

ただしbenchmark比較時にはORT version、OS、architecture、thread設定、optimization levelをrun-contextへ固定します。

## 3. CUDA

CUDAではprovider registrationだけでなく、dynamic library環境を含めて実行可能性を確認します。

主な失敗要因:

- CUDA runtime不一致
- cuDNN不一致
- cuBLAS loader不一致
- ORT package / CUDA major mismatch
- CPU fallbackによる見かけ上の成功

strict provider runでは可能な限りCPU fallbackを無効化します。

数値比較ではGPU固有のfloating-point差を「provider failure」と混同しません。CER/WER、token parity、numeric parityを別指標で扱います。

## 4. DirectML

DirectMLのhard constraint:

```text
execution_mode = sequential
enable_mem_pattern = false
```

理由:

- DirectML EPはparallel execution modeをサポートしない
- memory pattern optimizationを使用しない
- 同じInferenceSessionに対するconcurrent `Run` を前提にしない

runtime guardでもこれに反する設定を拒否します。

DirectMLはWindows上で評価します。HF JobsはLinux computeなので、HFはartifact/dataset供給源には使えてもDirectML execution environmentにはなりません。

CPU fallbackを許したDirectML runでinferenceが成功しても、DirectMLでnodeが実行された証明にはなりません。provider proofが必要なrunではstrict provider modeを使用します。

## 5. CoreML

CoreMLはmacOS / Apple Siliconを主対象とします。

区別する失敗:

- provider unavailable
- session registration failure
- graph shape incompatibility
- graph compilation failure
- runtime inference failure
- zero-dimension tensor
- numeric/parity failure

「dynamic shapeがある」こと自体と「zero dimensionが実行時に現れた」ことを同一エラーにしません。

CoreML対応可否をhuman metadataへ書かず、provider/session/runtime結果から評価します。

## 6. ORT optimization

診断時にはoptimization levelを明示的に切り替えられます。

```text
configured
disable
basic
extended
all
```

optimizer canaryでは少なくとも `ORT_DISABLE_ALL`, `ORT_ENABLE_BASIC`, `ORT_ENABLE_EXTENDED`, `ORT_ENABLE_ALL` の出力shape・finite・数値近似を比較します。

optimization levelを変えたrunは同じrun identityとして扱わず、run-context metadata/configへ残します。

## 7. Tensor sanity

providerに依存せず、runtime boundaryで次を拒否します。

- empty waveform
- non-finite waveform
- zero-sized output dimension
- NaN / Inf logits
- decoder state shape/dtypeの不整合
- Whisper cache transitionの不整合
- TDT duration/token logits dimensionの不整合

accelerator固有のsilent corruptionを「認識精度低下」として後段まで流さないためです。

## 8. Rust provider features

RustのORT EPはcompile-time featureで有効化されます。runtimeでprovider名が指定されても、binary側にfeatureが無ければcompiled=falseとしてfailさせます。

Rust evaluator自体のdecoder capabilityはCTCのみです。providerがCUDA/DirectML/CoreMLであることと、TDT/Whisper decoderが実装済みであることは無関係です。

## 9. Provider telemetry

結果へ記録する値は「観測したもの」だけです。

例:

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

node assignmentを計測していない場合は `null` とし、0を捏造しません。
