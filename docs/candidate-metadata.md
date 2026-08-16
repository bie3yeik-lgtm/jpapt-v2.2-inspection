# Candidate metadata / Runtime Contract

## 目的

`candidates/<candidate-id>/metadata.json`は、candidate内のartifact構成、decoder、runtime I/O、tokenizer/processor、必要runtime featureを決定する**正本**です。

評価workflowやCLIは、次のような推測を行いません。

```text
最初に見つかった*.onnxをmodelとみなす
vocabulary.jsonを名前だけで探す
Whisperだからencoder.onnxだとworkflow側で決める
CTCだからblank_idをsource codeへ固定する
```

代わりに、`CandidateArtifacts`が`metadata.json`を解決します。

```text
python/src/parakeet_onnx/runtime/artifacts.py
```

新規candidateは`schema_version = 2`必須です。既存のschema v1 CTC candidateは読み取り互換のみ残しています。

## 共通構造

```json
{
  "schema_version": 2,
  "candidate_id": "<prefix>-000002",
  "decoder": "ctc | tdt | whisper_autoregressive",
  "artifact_contract": "<contract-id>",
  "artifacts": {
    "<role>": {
      "path": "<candidate-relative-path>",
      "sha256": "<64 hex>",
      "size_bytes": 123
    }
  },
  "runtime_contract": {
    "decoder": "<same decoder>",
    "input_kind": "canonical_waveform | features",
    "io": {},
    "decoder_config": {}
  },
  "tokenizer": {
    "kind": "vocabulary | transformers_processor",
    "path": "<candidate-relative-path>"
  },
  "features": {
    "kv_cache": false,
    "multi_graph": false,
    "transformers_processor": false,
    "external_frontend": false,
    "timestamps": false
  }
}
```

JSON Schema:

```text
evaluation/schemas/candidate-metadata.schema.json
```

JSON Schemaは共通形を検査し、decoder固有I/Oはruntime contract parserが検査します。

## Candidate bundle SHA

単一ONNXだけをidentityにすると、TDT/Whisperのmulti-graph candidateを一意に表現できません。

そのため`CandidateArtifacts.bundle_sha256`は、全artifactについて次を安定順序でhashします。

```text
artifact role
candidate-relative path
artifact SHA-256
```

新規runでは、このbundle SHAをcandidateの評価/promotion identityとして使用します。

`run-context.artifact`は既存contractとの互換のためprimary artifactを保持し、完全なcandidate provenanceは次へ保存します。

```text
run-context.metadata.candidate
```

## CTC (`ctc-single-graph-v1`)

Bucket例:

```text
candidates/parakeet-ctc-candidate-000002/
├── README.md
├── metadata.json
├── model.onnx
└── vocabulary.json
```

`metadata.json`:

```json
{
  "schema_version": 2,
  "candidate_id": "parakeet-ctc-candidate-000002",
  "decoder": "ctc",
  "artifact_contract": "ctc-single-graph-v1",
  "artifacts": {
    "primary": {
      "path": "model.onnx",
      "sha256": "<MODEL_SHA256>",
      "size_bytes": 123456789
    }
  },
  "runtime_contract": {
    "decoder": "ctc",
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
    "kind": "vocabulary",
    "path": "vocabulary.json"
  },
  "features": {
    "kv_cache": false,
    "multi_graph": false,
    "transformers_processor": false,
    "external_frontend": false,
    "timestamps": false
  }
}
```

`blank_id`やtensor名は実際にexportされたgraphに合わせます。上記名称を固定値として流用してはいけません。

## TDT (`tdt-multi-graph-v1`)

現在のPython runtime contractはencoder / predictor / jointの3 roleを使用します。

```text
candidates/parakeet-tdt-candidate-000003/
├── README.md
├── metadata.json
├── encoder.onnx
├── predictor.onnx
├── joint.onnx
└── vocabulary.json
```

例:

```json
{
  "schema_version": 2,
  "candidate_id": "parakeet-tdt-candidate-000003",
  "decoder": "tdt",
  "artifact_contract": "tdt-multi-graph-v1",
  "artifacts": {
    "encoder": {
      "path": "encoder.onnx",
      "sha256": "<ENCODER_SHA256>",
      "size_bytes": 100
    },
    "predictor": {
      "path": "predictor.onnx",
      "sha256": "<PREDICTOR_SHA256>",
      "size_bytes": 100
    },
    "joint": {
      "path": "joint.onnx",
      "sha256": "<JOINT_SHA256>",
      "size_bytes": 100
    }
  },
  "runtime_contract": {
    "decoder": "tdt",
    "input_kind": "canonical_waveform",
    "io": {
      "encoder": {
        "input": "audio_signal",
        "length_input": "audio_length",
        "output": "encoded",
        "length_output": "encoded_length"
      },
      "predictor": {
        "token_input": "token",
        "output": "prediction",
        "state_inputs": ["h_in"],
        "state_outputs": ["h_out"],
        "state_shapes": [[1, 1, 640]],
        "state_dtypes": ["float32"]
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
      "durations": [0, 1, 2, 3, 4],
      "max_symbols_per_step": 10
    }
  },
  "tokenizer": {
    "kind": "vocabulary",
    "path": "vocabulary.json"
  },
  "features": {
    "kv_cache": false,
    "multi_graph": true,
    "transformers_processor": false,
    "external_frontend": false,
    "timestamps": false
  }
}
```

`predictor.state_inputs/state_outputs/state_shapes/state_dtypes`は実際のexported predictor stateに合わせます。

Jointがtoken/durationを1 tensorで返す場合は次を使えます。

```json
{
  "output_mode": "concatenated",
  "token_output": "joint_logits",
  "token_vocab_size": 1025
}
```

この場合、`duration_output`は不要です。

### 現在のTDT制約

Python側にはgreedy token-and-duration decodeとgeneric ORT adapterがあります。ただし現在のgeneric adapterは、

```text
input_kind = canonical_waveform
```

を対象とします。`input_kind = features`を使うTDT candidateにはmodel-specific frontend adapterが必要で、現capabilityでは`external_frontend=false`として拒否します。

また、実際のParakeet TDT export graphに対するcanonical NeMo parityは別途実candidateで確認する必要があります。

## Whisper (`whisper-autoregressive-v1`)

```text
candidates/whisper-candidate-000004/
├── README.md
├── metadata.json
├── encoder.onnx
├── decoder.onnx
├── decoder_with_past.onnx
└── tokenizer/
    └── <AutoProcessor assets>
```

例:

```json
{
  "schema_version": 2,
  "candidate_id": "whisper-candidate-000004",
  "decoder": "whisper_autoregressive",
  "artifact_contract": "whisper-autoregressive-v1",
  "artifacts": {
    "encoder": {
      "path": "encoder.onnx",
      "sha256": "<ENCODER_SHA256>",
      "size_bytes": 100
    },
    "decoder": {
      "path": "decoder.onnx",
      "sha256": "<DECODER_SHA256>",
      "size_bytes": 100
    },
    "decoder_with_past": {
      "path": "decoder_with_past.onnx",
      "sha256": "<DECODER_WITH_PAST_SHA256>",
      "size_bytes": 100
    }
  },
  "runtime_contract": {
    "decoder": "whisper_autoregressive",
    "input_kind": "features",
    "io": {
      "encoder": {
        "input": "input_features",
        "output": "last_hidden_state"
      },
      "decoder": {
        "input_ids": "input_ids",
        "encoder_hidden_states": "encoder_hidden_states",
        "logits_output": "logits",
        "past_outputs": [
          "present.0.decoder.key",
          "present.0.decoder.value"
        ]
      },
      "decoder_with_past": {
        "input_ids": "input_ids",
        "encoder_hidden_states": "encoder_hidden_states",
        "logits_output": "logits",
        "past_inputs": [
          "past_key_values.0.decoder.key",
          "past_key_values.0.decoder.value"
        ],
        "past_outputs": [
          "present.0.decoder.key",
          "present.0.decoder.value"
        ]
      }
    },
    "decoder_config": {
      "prompt_token_ids": [50258, 50266, 50360],
      "eos_token_id": 50257,
      "max_new_tokens": 448,
      "suppress_tokens": [],
      "skip_special_tokens": true,
      "timestamps": false
    }
  },
  "tokenizer": {
    "kind": "transformers_processor",
    "path": "tokenizer"
  },
  "features": {
    "kv_cache": true,
    "multi_graph": true,
    "transformers_processor": true,
    "external_frontend": true,
    "timestamps": false
  }
}
```

KV cache名はモデル/export方式によって増減します。上記2 tensorは構造例であり、実candidateでは**全cache input/outputを順序付き配列として記録**してください。

`decoder.past_outputs`の数と`decoder_with_past.past_inputs`の数は一致する必要があります。

### Processor

Whisper candidateは外部ネットワークからprocessorを暗黙取得しません。

```text
tokenizer.kind = transformers_processor
```

で指定されたcandidate-local pathを、

```python
AutoProcessor.from_pretrained(path, local_files_only=True)
```

として読みます。

### 現在のWhisper制約

Python runtimeには次を実装しています。

```text
processor -> input_features
encoder
initial decoder
decoder_with_past
KV-cache loop
greedy token selection
suppress_tokens
EOS termination
tokenizer decode
```

一方、現capabilityでは以下を未対応として明示します。

```text
timestamps = false
```

Timestamp-aware decodeを実装するまでは、`features.timestamps=true`のcandidateは評価前に拒否されます。

実際のKotoba Whisper candidateに対するTransformers parityは、実graph作成後に検証する必要があります。

## Evaluator capabilityとの対応

Candidateは必要機能を`features`で宣言します。

Evaluatorは次でdecoderごとの能力を宣言します。

```text
config/evaluators/python-onnx.toml
config/evaluators/rust-onnx.toml
```

例:

```toml
[decoder_features.whisper_autoregressive]
kv_cache = true
multi_graph = true
transformers_processor = true
external_frontend = true
timestamps = false
```

評価前に、

```text
scripts/ci/validate-evaluator-capability.py
```

が以下をまとめて検証します。

```text
decoder
provider
artifact_contract
decoder-specific runtime contract
required features
artifact SHA/size
```

## Publish

新規candidateは次でpublishします。

```bash
bash scripts/hf/hf-push-candidate.sh <candidate-directory> [prefix]
```

このscriptは採番前にschema-v2 metadataとruntime contractを検証します。無効なcandidateで連番を消費しません。

正式ID取得後に`metadata.json.candidate_id`を書き換え、再検証してからBucketへuploadします。
