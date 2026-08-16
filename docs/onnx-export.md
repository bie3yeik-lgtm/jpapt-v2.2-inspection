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
Central Candidate Allocation
  ↓
Candidate Publish
```

NeMo/Transformersで異なるのはexport adapterとgraph構成であり、candidate lifecycleと採番方法は同じです。

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

NeMo modelを固定revisionでloadし、CTC/TDT向けgraphを生成します。

CTCでは単一primary ONNX artifactで成立する場合があります。

```text
model.onnx
metadata.json
vocabulary.json
```

TDTではpredictor/joint等のruntime contractを追加で考慮します。

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

複数graphの役割はファイル名だけに依存せず、candidate metadataで明示します。

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

ローカルexport時点ではcandidate連番を決めません。

```text
tmp/export/work/
candidate_id = unallocated
```

正式IDはBucket publish時に中央Allocatorが発行します。

```bash
HF_BUCKET=owner/dev-bucket \
HF_TARGET_ID=<target-id> \
  bash scripts/hf/hf-push-candidate.sh ./tmp/export/work
```

内部:

```text
hf-push-candidate.sh
  ↓
hf-request-id.sh
  ↓
HF Central Sequence Allocator
  ↓
candidates/<prefix>-NNNNNN/README.md予約
  ↓
metadata.json candidate_id更新
  ↓
artifact sync
```

複数Repositoryから同じBucketへpublishしても採番は中央で直列化されます。

他Repositoryから利用する場合は、中央Allocator Repositoryへアクセス可能な`HF_ALLOCATOR_GITHUB_TOKEN`を設定します。

## 予約番号の扱い

中央Allocatorがcandidate IDを予約した後にartifact uploadが失敗しても、そのsuffixは再利用しません。

BucketルートREADMEには「Allocatorが予約済みの現在最大candidate番号」が表示されます。これは「publish成功済み最大番号」とは限りません。

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

Candidate publish前後の代表項目:

```text
ONNX structural validation
artifact SHA-256
input/output contract
CPU session creation where applicable
reference parity checkpoint
decoder/token/text parity
config version / revision provenance
```

最終transcript一致だけでconversion correctnessを判断しません。

## Dynamic shape

ASRは可変長入力を扱うため、必要なtime dimensionはdynamicに保ちます。Provider固有問題が出た場合、まずgraph/operator/provider compatibilityを調査し、安易にOSごとの別モデルへ分岐しないことを基本とします。

## Evaluator capabilityとの関係

Candidateを保存できることと、現在のevaluatorで実行できることは別です。

```text
candidate.decoder
  ↓
config/evaluators/<evaluator>.toml
  ↓
validate-evaluator-capability.py
```

現在はPython/Rust ONNX evaluatorともCTC capabilityを宣言しています。Whisper/TDT artifactをBucketへ保存できても、runtime capabilityが追加されるまでは評価開始前に明示的に停止します。

## 現在の実装状況

```text
NeMo/Parakeet CTC                 主要runtime/evaluation path
Parakeet TDT                      target contractあり、runtime未完成
Transformers/Whisper reference    対応
Whisper autoregressive evaluator  未完成
```

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

関連文書:

```text
docs/central-allocator.md
docs/multi-framework-asr.md
docs/evaluation.md
```
