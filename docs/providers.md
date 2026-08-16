# Execution Providers

## 原則

Execution Providerについて次の段階を区別する。

```text
compiled
  ↓
registered / session_created
  ↓
execution_proven
  ↓
assignment_proven
```

上位段階を下位段階の証拠から推測しない。

## CPU

CPU providerはbaselineであり、successful inference自体をexecution proofとして扱える。

```text
requested=cpu
registered=true
execution_proven=true   # successful inferenceがある場合
fallback_detected=false
```

## CUDA / DirectML / CoreML

accelerator providerではsession作成成功だけではexecution proofではない。

```text
provider registered
session created
```

から、

```text
actual graph/node assignment
accelerator execution
```

を推測しない。

CPU fallbackを許可したsessionでinferenceが成功してもrequested EPが使われた証拠にはならない。

## Strict provider mode

CPU fallbackを無効化してaccelerator sessionでinference成功した場合、少なくとも「fallbackなしで実行できた」証拠にはなる。ただしnode assignmentの詳細を測定していないなら`assignment_proven`をtrueへ上げない。

## CoreML

CoreMLではgraph compile/session registrationと実node assignmentを分離する。CPU-assigned nodeが検出され、strict modeでCPU fallbackを禁止している場合はstrict rejectとする。

「CoreML EPがprovider listに存在した」ことをCoreML実行成功とは書かない。

## DirectML

DirectMLも同様に、Windows上でprovider registration/session creationが通っただけではassignment proofではない。profiling等のevidenceがない限り`assigned_nodes`を創作しない。

## Quality comparisonとの関係

NeMo↔ONNX quality comparisonはprovider quality差も測定できるが、まずCPUをcanonical conversion quality baselineとして使用することを推奨する。

```text
NeMo reference
  vs
CPU ONNX
```

で変換忠実度を確認した後、同じcandidateをCUDA/DirectML/CoreMLで評価する。

これにより、

```text
export/model差
provider数値差
provider fallback問題
```

を同時に混ぜない。

## Provider evidenceの保存

`run-context.json`と`metrics.json`にはrequested provider、registration、execution/fallback evidenceを保存する。

不明な値を都合よくfalseへ落とさない。contract上nullableである旧fieldが残る場合でも、意味として「未測定」と「false」を区別する。新しいstrict contractへ移行する際はenum/evidence objectへ寄せることを優先する。
