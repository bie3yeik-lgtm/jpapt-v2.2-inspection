# ONNX ExportとCandidate生成

## 基本方針

ONNXはcanonical sourceではなくdeployment artifactです。Export元はtargetの`reference.json`で固定された`upstream`と`tokenizer`です。

```text
Versioned Config
  ↓
Upstream + Tokenizer
  ↓
Framework-specific Export Adapter
  ↓
Local Export
  ↓
Candidate Publish
```

NeMo/Transformersで異なるのはexport adapterとgraph構成であり、candidate lifecycleは同じです。

## 使用するrevision

`.ci/hf/config/revisions/reference.json`から次を使います。

```text
upstream.repo_id / revision
tokenizer.repo_id / revision
reference.canonical_framework
reference.revision
decoders
```

`development_artifact.revision`はexport元checkpointではありません。これはdevelopment artifact Model Repo側のsnapshotを表します。

floatingな`main`、`latest`、暗黙HEADをcanonical exportに使用しないでください。

## Framework差分

### NeMo / Parakeet

代表的にはNeMo modelを固定revisionでloadし、CTC/TDT向けgraphを生成します。

CTCでは単一primary ONNX artifactで成立する場合があります。

```text
model.onnx
metadata.json
vocabulary.json
```

TDTではpredictor/joint等のruntime contractを追加で考慮する必要があります。

### Transformers / Whisper

Transformers modelとprocessor/tokenizerをそれぞれ固定revisionでloadします。

Whisperは複数graphになることがあります。

```text
encoder.onnx
decoder.onnx
decoder_with_past.onnx
metadata.json
tokenizer/
```

複数graphの役割はファイル名だけに依存せず、candidate metadataで明示してください。

## Audio / Frontend境界

共通入力:

```text
CanonicalAudio
float32 / mono / 16 kHz
```

frontendをONNX外に置くかgraph内に含めるかはcandidate runtime contractの一部です。

### Frontend外部

```text
CanonicalAudio
  ↓
frontend
  ↓
features
  ↓
ONNX
```

### Frontend内包

```text
CanonicalAudio
  ↓
frontend + model ONNX
```

どちらを採用しても、reference/candidate parityで同じ境界を比較できるようmetadataへ記録します。

## Local exportと正式Candidate ID

ローカルexport時点では人間がcandidate連番を決めません。

```text
tmp/export/work/
```

metadataのcandidate IDは暫定`unallocated`でも構いません。

正式IDはBucket publish時に発行します。

```bash
HF_BUCKET=owner/dev-bucket \
HF_TARGET_ID=<target-id> \
  bash scripts/hf/hf-push-candidate.sh ./tmp/export/work
```

生成例:

```text
<target-or-purpose>-candidate-000002
```

採番は`candidates/`全体の最大suffix+1です。

## Candidate metadata

metadataは少なくとも次を表現できる必要があります。

```text
candidate_id
primary artifact
artifact roles
decoder
artifact SHA-256
runtime input/output contract
```

複数graphの場合も1つのcandidate IDの下へまとめます。

## Validation

Candidate publish前後に確認する代表項目:

```text
ONNX structural validation
artifact SHA-256
input/output contract
CPU session creation where applicable
reference parity checkpoint
decoder/token/text parity
config version / revision provenance
```

最終transcript一致だけでconversion correctnessを判断しないでください。

## Dynamic shape

ASRは可変長入力を扱うため、必要なtime dimensionはdynamicに保ちます。Provider固有問題が出た場合、まずgraph/operator/provider compatibilityを調査し、安易にOSごとの別モデルへ分岐しないことを基本とします。

## 現在の実装状況

- NeMo/Parakeet CTC: 現在の主要runtime/evaluation path
- Parakeet TDT: target contractはあるがruntime実装は未完成
- Transformers/Whisper: reference/config/storageは対応、autoregressive ONNX evaluatorは未完成

したがって、Whisper candidateを保存するBucket構造は既に共通化されていますが、評価runtimeがCTCと同等に完成しているわけではありません。

## Promotion

```text
Candidate
  ↓
Experiment / Run
  ↓
Smoke / Parity / Full
  ↓
Acceptance
  ↓
Artifact SHA一致確認
  ↓
HF Model Repo
```

Exporterから直接Model Repoへreleaseしません。