# JSON Contract 正規化設計

## 目的

本Repositoryでは、同じ意味を複数のJSON/TOML/Workflowへコピーする運用を禁止します。

従来は次の値が複数箇所へ重複していました。

```text
decoder = ctc / tdt / whisper_autoregressive
artifact contract
required artifact roles
tokenizer kind
runtime feature requirements
candidate / experiment / config のID prefix
supported/default decoder
```

これらは個々のcandidateやrunの事実ではなく、**再利用可能なASR runtime profileの意味**です。したがってSource of Truthを次へ集約します。

```text
config/asr-catalog.json
```

一方、次の値は中央化してはいけません。

```text
artifact path
artifact SHA-256
artifact size
tensor input/output name
blank_id / bos_id / prompt token IDs
predictor state shape/dtype
KV-cache tensor binding
upstream/model/tokenizer revision
dataset revision
実行時に選択されたvariant/provider
```

これらは特定artifact、特定config、特定runの**immutable fact**であり、中央のmutable catalogへ移すと過去の再現性を失うためです。

---

## 1. 設計原則

値をどこへ置くべきかは次の問いで決めます。

### 中央化する

次の条件を満たす値は中央catalogへ置きます。

1. 複数target/candidate/workflowで再利用される
2. 個別artifactを観測しなくても決定できる
3. 名前・分類・必要能力などのpolicy/semanticsである
4. 同じ値を複数ファイルへコピーすると同期漏れが起きる

### 個別ファイルへ固定する

次の条件を満たす値は中央化しません。

1. 特定artifactをbuild/exportした結果として決まる
2. SHA/revision/tensor bindingなど再現性の根拠になる
3. 将来catalogが変わっても過去のrunを同一条件で復元する必要がある
4. そのファイル自身のidentity/provenanceである

### Runへsnapshotする

mutable routingや選択値は、中央定義を参照して実行した後にrunへsnapshotします。

```text
中央定義        config/asr-catalog.json / HF_TARGETS_JSON
選択            runtime_variant / provider / config_version
実行snapshot    run-context.json
```

---

## 2. Source of Truth一覧

| 情報 | Source of Truth | 理由 |
|---|---|---|
| ID prefix文字列 | `config/asr-catalog.json.id_prefixes` | 命名policyであり個別runの事実ではない |
| decoder名 | `decoder_profiles.*.decoder` | runtime profileの意味 |
| artifact contract ID | `decoder_profiles.*.artifact_contract` | profile仕様 |
| required artifact roles | `decoder_profiles.*.required_artifact_roles` | profile仕様 |
| tokenizer kind | `decoder_profiles.*.tokenizer_kind` | profile仕様 |
| required runtime features | `decoder_profiles.*.features` | candidate要求仕様 |
| CTC/TDTなどの使い分け | `profile_sets.*.variants` | 同一target内のruntime選択肢 |
| default variant | `profile_sets.*.default_variant` | runtime選択policy |
| targetが使うprofile set | `config/hf-targets/*.toml [runtime].profile_set` | targetとruntime familyの関係 |
| config versionが使うprofile set | Bucket `runtime.json` | config snapshotとcatalog snapshotの関係 |
| artifact path/SHA/size | candidate `metadata.json` | candidate固有identity |
| tensor I/O binding | candidate `metadata.json` | export graph固有 |
| token/state/KV設定 | candidate `metadata.json` | export/runtime固有 |
| upstream/reference/tokenizer revision | `reference.json` | model provenance |
| evaluation schema identity/threshold | `evaluation-schema.json` | 評価規則 |
| dataset revision | `datasets-lock.json` | dataset provenance |
| current config version | `config/current.json` | mutable pointer |
| target→Bucket routing | `HF_TARGETS_JSON` | 現在routing |
| 実行時routing/variant | `run-context.json` | 過去再現snapshot |

---

## 3. Central ASR Catalog

```text
config/asr-catalog.json
```

catalogは3種類の情報だけを保持します。

```text
id_prefixes
    semantic key -> 表示prefix

decoder_profiles
    reusable runtime requirement

profile_sets
    target/candidateが利用できるvariant集合
```

例:

```json
{
  "schema_version": 1,
  "catalog_id": "asr-catalog-v1",
  "id_prefixes": {
    "candidate.parakeet": "parakeet-candidate",
    "experiment.cpu_full": "cpu-full-eval",
    "config.version": "config"
  },
  "decoder_profiles": {
    "ctc-v1": {
      "decoder": "ctc",
      "artifact_contract": "ctc-single-graph-v1",
      "tokenizer_kind": "vocabulary",
      "required_artifact_roles": ["primary"],
      "features": {
        "kv_cache": false,
        "multi_graph": false,
        "transformers_processor": false,
        "external_frontend": false,
        "timestamps": false
      }
    },
    "tdt-v1": {
      "decoder": "tdt",
      "artifact_contract": "tdt-multi-graph-v1",
      "tokenizer_kind": "vocabulary",
      "required_artifact_roles": ["encoder", "predictor", "joint"],
      "features": {
        "kv_cache": false,
        "multi_graph": true,
        "transformers_processor": false,
        "external_frontend": false,
        "timestamps": false
      }
    }
  },
  "profile_sets": {
    "parakeet-tdt-ctc-v1": {
      "candidate_prefix_key": "candidate.parakeet",
      "variants": {
        "ctc": "ctc-v1",
        "tdt": "tdt-v1"
      },
      "default_variant": "ctc"
    }
  }
}
```

`candidate.parakeet`や`experiment.cpu_full`はsemantic keyです。Workflowやscriptは`parakeet-candidate`や`cpu-full-eval`という表示文字列を直接保持してはいけません。

---

## 4. Target TOML

Target側はdecoder一覧を持ちません。

```toml
schema_version = 2

[target]
id = "parakeet-tdt_ctc-0.6b-ja"
model_id = "parakeet-tdt_ctc-0.6b-ja"

[upstream]
repo_id = "nvidia/parakeet-tdt_ctc-0.6b-ja"

[reference]
canonical_framework = "nemo"

[runtime]
profile_set = "parakeet-tdt-ctc-v1"
```

次は不要です。

```toml
[decoders]
supported = ["ctc", "tdt"]
default = "ctc"
```

これらは`profile_set`から導出されます。

---

## 5. Config Version

### Normalized layout

```text
config/versions/config-NNNNNN/
├── reference.json
├── evaluation-schema.json
├── datasets-lock.json
└── runtime.json
```

### reference.json

model provenanceだけを保持します。

```json
{
  "schema_version": 1,
  "development_artifact": {
    "repo_id": "namespace/development-model",
    "revision": "<COMMIT_SHA>"
  },
  "upstream": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision": "<UPSTREAM_SHA>"
  },
  "tokenizer": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision": "<TOKENIZER_SHA>"
  },
  "reference": {
    "id": "nemo-reference-v1",
    "revision": "<REFERENCE_IMPLEMENTATION_REVISION>",
    "canonical_framework": "nemo"
  }
}
```

`decoders`は記述しません。

### evaluation-schema.json

評価規則だけを保持します。

```json
{
  "schema_version": 1,
  "schema": {
    "id": "asr-evaluation-v1",
    "revision": "<SCHEMA_REVISION>"
  }
}
```

threshold等が必要ならこの文書に保持しますが、decoder一覧は置きません。

### runtime.json

人間がdecoder一覧を複製する代わりに、profile setを参照します。

```json
{
  "schema_version": 1,
  "catalog": {
    "id": "asr-catalog-v1",
    "sha256": "<CATALOG_SHA256>"
  },
  "profile_set": "parakeet-tdt-ctc-v1"
}
```

`runtime.json`は原則手書きしません。

```bash
python scripts/ci/write-runtime-lock.py \
  --profile-set parakeet-tdt-ctc-v1 \
  --output runtime.json
```

`hf-push-config-version.sh`が自動生成します。

catalog SHAをlockする理由は、`profile_set`という名前が将来同じでも中身が変更された場合に、過去configの意味が silently change することを防ぐためです。

---

## 6. Candidate Metadata v3

Candidateは「runtime profileの意味」を繰り返しません。

### Parakeet CTC + TDTを同一candidateに保持

```json
{
  "schema_version": 3,
  "candidate_id": "parakeet-candidate-000002",
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "profile": "ctc-v1",
      "artifacts": {
        "primary": {
          "path": "ctc/model.onnx",
          "sha256": "<CTC_SHA256>",
          "size_bytes": 123456
        }
      },
      "bindings": {
        "input_kind": "canonical_waveform",
        "io": {
          "primary": {
            "input": "audio_signal",
            "length_input": "length",
            "logits_output": "logits"
          }
        },
        "decoder_config": {
          "blank_id": 1024
        }
      },
      "tokenizer": {
        "path": "tokenizer/vocabulary.json"
      }
    },
    "tdt": {
      "profile": "tdt-v1",
      "artifacts": {
        "encoder": {
          "path": "tdt/encoder.onnx",
          "sha256": "<ENCODER_SHA256>",
          "size_bytes": 123
        },
        "predictor": {
          "path": "tdt/predictor.onnx",
          "sha256": "<PREDICTOR_SHA256>",
          "size_bytes": 123
        },
        "joint": {
          "path": "tdt/joint.onnx",
          "sha256": "<JOINT_SHA256>",
          "size_bytes": 123
        }
      },
      "bindings": {
        "input_kind": "canonical_waveform",
        "io": {
          "encoder": {
            "input": "audio_signal",
            "output": "encoded"
          },
          "predictor": {
            "token_input": "token",
            "output": "prediction",
            "state_inputs": [],
            "state_outputs": [],
            "state_shapes": [],
            "state_dtypes": []
          },
          "joint": {
            "encoder_input": "encoder_frame",
            "predictor_input": "prediction",
            "token_output": "token_logits",
            "duration_output": "duration_logits",
            "output_mode": "separate"
          }
        },
        "decoder_config": {
          "blank_id": 0,
          "bos_id": 1,
          "durations": [0, 1, 2, 3, 4]
        }
      },
      "tokenizer": {
        "path": "tokenizer/vocabulary.json"
      }
    }
  }
}
```

ここに次は書きません。

```text
decoder
artifact_contract
tokenizer.kind
features
```

`profile`からすべて導出できます。

一方、次はcandidateに残します。

```text
artifact path/SHA/size
input/output tensor binding
blank_id/bos_id/durations
predictor state
KV-cache binding
processor/tokenizer path
```

これらはexportした実artifactを見なければ決まらないためです。

---

## 7. CTC/TDTの切替

JSONを書き換えません。

### CLI

```bash
python -m parakeet_onnx.cli.evaluate \
  --runtime-variant ctc \
  ...
```

または、

```bash
python -m parakeet_onnx.cli.evaluate \
  --runtime-variant tdt \
  ...
```

### Environment

```bash
ASR_RUNTIME_VARIANT=tdt
```

### GitHub Actions

`runtime_variant` workflow inputへ、

```text
ctc
tdt
```

のいずれかを渡します。

空なら中央catalogの`default_variant`が使用されます。

解決経路:

```text
HF Target
  ↓ profile_set
ASR Catalog
  ↓ runtime_variant
Decoder Profile
  ↓
Candidate variants.<runtime_variant>
  ↓
artifact bindings
```

---

## 8. ID Prefixの中央化

Workflowは次のようなraw prefixを使いません。

```bash
# 禁止
hf-allocate-id.sh experiments cpu-full-eval
```

代わりにsemantic keyを使います。

```bash
hf-allocate-id.sh experiments experiment.cpu_full
```

Allocatorが、

```text
experiment.cpu_full
        ↓ config/asr-catalog.json
cpu-full-eval
        ↓ max suffix + 1
cpu-full-eval-000123
```

と解決します。

prefix文字列の変更はcatalogの1箇所だけで行います。

---

## 9. Evaluator Capabilityをcatalogへ統合しない理由

次の2つは似ていますが意味が逆です。

```text
ASR Catalog
    candidate/runtimeが要求する能力

config/evaluators/*.toml
    evaluator implementationが実際に提供できる能力
```

例えばTDT profileが`multi_graph=true`を要求していても、Rust evaluatorがTDT未対応ならRust capabilityはそれを提供しません。

したがって両者を1つへまとめると、要求仕様と実装能力を混同します。

評価前に、

```text
Profile requirement
       ∩
Evaluator capability
       ↓
実行可能か判定
```

します。

これは意味上必要な二重記述であり、冗長なコピーではありません。

---

## 10. Immutable / Mutableの境界

### Git管理・中央catalog

```text
config/asr-catalog.json
config/hf-targets/*.toml
config/evaluators/*.toml
```

### Bucket immutable config

```text
config/versions/config-NNNNNN/
```

### Bucket mutable pointer

```text
config/current.json
```

### Candidate immutable build facts

```text
candidates/<candidate-id>/metadata.json
```

### Runtime immutable snapshot

```text
runs/<run-id>/run-context.json
```

この分離により、中央catalogや`HF_TARGETS_JSON`が将来変更されても、過去runはrun-contextとconfig lockから再現できます。

---

## 11. 新規追加時のルール

新decoder/runtime familyを追加するときは、次の順序にします。

1. `config/asr-catalog.json.decoder_profiles`へprofile追加
2. 必要なら`profile_sets`へvariant追加
3. runtime adapter/evaluator implementationを追加
4. evaluator capabilityを拡張
5. candidateには新variantのartifact/bindingsだけを追加

次のファイルへdecoder名を個別追加してはいけません。

```text
reference.json
evaluation-schema.json
workflow YAML
candidate metadata top-level
HF target decoders table
```

これが本RepositoryのJSON/TOML正規化規則です。
