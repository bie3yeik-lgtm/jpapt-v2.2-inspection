# Operational Workflows

この文書は、現行repositoryで **config versionを作る → candidateをpublishする → 評価する → run/benchmarkを保存する → accepted candidateをpromotionする** までの運用フローを説明します。GitHub Actionsの個別仕様は [github-actions.md](./github-actions.md) を参照してください。

## 1. 運用原則

- human-authored入力は必要最小限にする。
- target/Bucket/model/upstream/runtime profile/decoderはsource-controlled configとASR catalogから導出する。
- candidate/config/experiment IDは中央Allocatorで採番し、人がsuffixを選ばない。
- new writeはcanonical layoutだけを使用する。
- historical Bucket layoutはread-only fallbackとしてのみ解釈する。
- persistent execution artifactはRust contract validatorで再検証する。
- PythonはONNX/Transformers/NeMo/HF datasets等のPython-native boundaryに限定する。
- network/authは公式 `hf` / `gh` CLIを利用する。

## 2. Target resolution

最初のoperator inputは通常 `hf_target` です。

```bash
cargo run --quiet --locked -p asr-hf -- \
  resolve-target \
  --target parakeet-tdt_ctc-0.6b-ja
```

runtime variantを明示する場合:

```bash
cargo run --quiet --locked -p asr-hf -- \
  resolve-target \
  --target parakeet-tdt_ctc-0.6b-ja \
  --runtime-variant ctc
```

省略時は `config/asr-catalog.json` のprofile-set default variantを使います。

resolverが確定する主な値:

```text
HF_TARGET_ID
HF_BUCKET
HF_MODEL_REPO
EXPECTED_DEVELOPMENT_REPO_ID
EXPECTED_UPSTREAM_REPO_ID
EXPECTED_TOKENIZER_REPO_ID
EXPECTED_FRAMEWORK
HF_PROFILE_SET
ASR_RUNTIME_VARIANT
EXPECTED_RUNTIME_PROFILE
EXPECTED_DECODER
```

## 3. Config version publish

### Human-authored source

source directoryへ3文書を用意します。

```text
revision-source/
├── reference.json
├── evaluation-schema.json
└── datasets-lock.json
```

`runtime.json` は手書きしません。

### Publish

```bash
export HF_TOKEN=...
export HF_TARGET_ID=parakeet-tdt_ctc-0.6b-ja

bash scripts/hf/hf-push-config-version.sh ./revision-source
```

実処理:

1. target/profile setをRustで解決
2. 3 human-authored documentを検証
3. catalog fingerprintから `runtime.json` をRustで生成
4. 4-document revision bundleをvalidation
5. bundle SHAを計算
6. central allocatorへ `config` allocationを要求
7. `config/versions/config-NNNNNN/` へpublish
8. `config/current.json` を更新

canonical path:

```text
config/versions/config-NNNNNN/
├── README.md
├── reference.json
├── evaluation-schema.json
├── datasets-lock.json
└── runtime.json
```

## 4. Config fetch

```bash
bash scripts/hf/hf-fetch-revisions.sh
```

local:

```text
.ci/hf/config/
├── current.json
├── resolved.json
└── revisions/
    ├── reference.json
    ├── evaluation-schema.json
    ├── datasets-lock.json
    └── runtime.json
```

`resolved.json` は「どのconfig versionを実際に選択したか」をfreezeします。

override:

```bash
export HF_CONFIG_VERSION=config-000123
bash scripts/hf/hf-fetch-revisions.sh
```

この場合 `selection_source=override` になります。

## 5. Candidate作成

human-authored candidate metadataは最小形です。

Parakeet hybrid例:

```json
{
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "artifacts": {"primary": "ctc/model.onnx"},
      "tokenizer": "tokenizer/vocabulary.json"
    },
    "tdt": {
      "artifacts": {
        "encoder": "tdt/encoder.onnx",
        "predictor": "tdt/predictor.onnx",
        "joint": "tdt/joint.onnx"
      },
      "tokenizer": "tokenizer/vocabulary.json"
    }
  }
}
```

candidate ID、hash、size、decoder、profile、graph binding、blank/BOS/cache/duration semanticsは書きません。

## 6. Candidate contract inspection

Python-native ONNX inspection boundary:

```bash
python scripts/ci/resolve-candidate-artifacts.py \
  --candidate-dir ./candidate \
  --runtime-variant ctc \
  --contract-out .ci/candidate-contract.json
```

ここで実artifactからgenerated contractを確定します。そのcontractはRust policyでも検証されます。

## 7. Candidate publish

```bash
export HF_TOKEN=...
export HF_TARGET_ID=parakeet-tdt_ctc-0.6b-ja

bash scripts/hf/hf-push-candidate.sh ./candidate
```

実処理:

1. candidate sourceをcanonical local pathとして解決
2. `.candidate-id` がsourceに存在しないことを確認
3. metadata/profile setを検証
4. Python-native ONNX runtime contract inspection
5. Rust側candidate/HF policy validation
6. central allocatorへ `candidates` allocationを要求
7. canonical ID `candidate-NNNNNN` を取得
8. `hf buckets sync --plan` を生成
9. planをRustで検証し、fresh `upload` 以外を拒否
10. canonical pathへapply

新規write:

```text
candidates/candidate-NNNNNN/
```

以下は新規生成しません。

```text
candidates/ctc/candidate-NNNNNN/
candidates/tdt/candidate-NNNNNN/
```

## 8. Candidate selection / fetch

明示ID:

```bash
bash scripts/hf/hf-fetch-candidate.sh candidate-000124
```

workflowでIDを省略した場合:

1. `hf buckets list .../candidates -R -q`
2. Rust `resolve-candidate-location`
3. canonical candidateが存在すれば最新canonicalを選択
4. canonicalが無いhistorical Bucketのみvariant配下をfallback解決

resolverはHF CLIが次のどちらを返しても正規化します。

```text
ctc/candidate-000001/metadata.json
candidates/ctc/candidate-000001/metadata.json
```

fetch後local candidateには `.candidate-id` がmaterializeされます。

## 9. Experiment allocation

評価workflowはrunの前に `experiments` collectionからIDを採番します。

```bash
bash scripts/hf/hf-allocate-id.sh experiments
```

canonical ID:

```text
experiment-NNNNNN
```

workflow種別、provider、candidate、evaluation名をID prefixへ埋め込みません。これらはgenerated metadata/run-contextで保持します。

## 10. Python evaluation

Python evaluatorはCTC/TDT/Whisper autoregressiveを扱います。

標準flow:

```text
resolve target
  ↓
fetch revisions
  ↓
fetch candidate
  ↓
CandidateArtifacts / ONNX inspection
  ↓
dataset manifest resolution/materialization
  ↓
run-context freeze
  ↓
Python evaluator
  ↓
run-context.json
samples.jsonl
metrics.json
run.parquet
```

代表workflow:

- `cpu-full-eval.yml`
- `cross-platform-parity.yml`

## 11. Rust evaluation

Rust evaluatorは現時点でCTCのみです。

```text
candidate
  ↓ Python ONNX inspection boundary
GeneratedCandidateContract
  +
HF dataset
  ↓ Python datasets boundary
ResolvedManifest
  ↓
Rust asr-contracts build-run-context
  ↓
Rust asr-eval evaluate
  ↓
Rust validate-run
```

代表CLI:

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  build-run-context \
  --repository-root . \
  --model parakeet-tdt_ctc-0.6b-ja \
  --provider cpu \
  --evaluation smoke \
  --environment linux \
  --revisions .ci/hf/config/revisions \
  --candidate-contract .ci/candidate-contract.json \
  --runtime-variant ctc \
  --experiment-id experiment-000125 \
  --optimization-level configured \
  --output .ci/run-context.json
```

strict accelerator proofではnon-CPU providerに `--strict-provider` を追加します。

## 12. Result validation

run directory:

```text
results/<run>/
├── run-context.json
├── samples.jsonl
├── metrics.json
└── run.parquet
```

Rust validation:

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  validate-run results/<run>
```

`run.parquet` はExperimentCapsuleV1のdurable analytical representationです。大きなmodel/audioをParquetへ複製せず、external artifact referenceを保持します。

## 13. Run publish

```bash
bash scripts/hf/hf-push-run.sh results/<run>
```

remote:

```text
runs/<run-id>/
```

upload前にJSON/JSONL contract、run identity、ExperimentCapsuleV1整合性を検証します。run upload wrapperはremote削除を目的とした `--delete` を使用しません。

## 14. Benchmark publish

```bash
bash scripts/hf/hf-push-benchmark.sh \
  results/<run>/metrics.json \
  linux-cpu-full
```

remote:

```text
benchmarks/<candidate-id>/<benchmark-name>/<run-id>.json
```

benchmark documentは軽量indexであり、full runの代替ではありません。

## 15. Provider proof

strict provider modeで確認したいのは「providerを登録できた」ではなく、CPU fallbackなしで対象provider executionが成立したかです。

CoreMLについては `provider-strict-probes.yml` がsynthetic CTC fixtureを使ってreadiness evidenceを生成します。DirectMLはretiredでprobe対象外です。

provider state:

```text
compiled
registered
session_created
execution_proven
assignment_proven
```

各段階を同一視しません。

## 16. Promotion

```bash
bash scripts/hf/hf-promote-candidate.sh \
  candidate-000124 \
  results/<accepted-full-run>
```

標準gate:

```text
run-context valid
metrics valid
run ID一致
candidate ID一致
candidate bundle SHA一致
acceptance.passed == true
evaluation_id == full
```

promotionはBucket candidateを再fetchし、runtime contractとbundle hashを再検証してからModel Repoへuploadします。

release stagingへ代表的に以下を含めます。

```text
candidate artifacts
run-context.json
metrics.json
promotion.json
```

成功後、run側にも `promotion.json` を記録します。

## 17. GitHub Actionsでの実行

### Full CPU

Actions -> `CPU Full Evaluation`

- targetを選ぶ
- candidate blankなら最新を自動選択
- runtime variant blankならcatalog default
- Linux CPUで`full`
- run + benchmarkをHFへpublish

### Python cross-platform parity

Actions -> `Cross Platform ONNX Parity`

- Linux CPU
- Windows CPU
- macOS CPU
- macOS CoreML

### Rust CTC matrix

Actions -> `Rust Cross Platform Evaluation`

- Linux CPU
- Windows CPU
- macOS CPU
- macOS CoreML
- strict provider / optimization levelをinputで制御

詳細なinputs/secrets/artifactsは [github-actions.md](./github-actions.md)。

## 18. Config / candidate / runのimmutable policy

### Immutable-by-policy

```text
config/versions/config-NNNNNN/
candidates/candidate-NNNNNN/
runs/<run-id>/
```

同じidentityへ別内容を上書きして「最新化」しません。

### Mutable pointer/status

```text
config/current.json
Bucket root README managed block
```

mutable objectとimmutable execution evidenceを分離します。

## 19. 変更後のvalidation順序

```text
1. source-controlled config/schema/catalog
2. cargo fmt/check/clippy/test
3. Python unit/reference boundary tests
4. Validate HF Layout
5. Capsule Interop (capsule変更時)
6. provider strict probe (provider/runtime変更時)
7. public-model E2E (model/runtime/reference変更時)
8. production candidate evaluation
9. promotion
```

CIの都合でhuman-authored inputを増やしたり、generated stateをconfigへコピーしたりしないことが重要です。
