# Candidate Metadata v3 / Runtime Variant

## 目的

`candidates/<candidate-id>/metadata.json` は、candidate固有のartifact identityとruntime bindingを保存する正本です。

ただしdecoderの意味そのものはcandidateへ複製しません。

```text
Reusable semantics
    config/asr-catalog.json

Candidate-specific facts
    candidates/<candidate-id>/metadata.json
```

詳細な正規化原則は [`json-contract-design.md`](./json-contract-design.md) を参照してください。

---

## Canonical schema

新規candidateは `schema_version = 3` 必須です。

```json
{
  "schema_version": 3,
  "candidate_id": "parakeet-candidate-000002",
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "profile": "ctc-v1",
      "artifacts": {},
      "bindings": {
        "input_kind": "canonical_waveform",
        "io": {},
        "decoder_config": {}
      },
      "tokenizer": {
        "path": "tokenizer/vocabulary.json"
      }
    },
    "tdt": {
      "profile": "tdt-v1",
      "artifacts": {},
      "bindings": {
        "input_kind": "canonical_waveform",
        "io": {},
        "decoder_config": {}
      },
      "tokenizer": {
        "path": "tokenizer/vocabulary.json"
      }
    }
  }
}
```

JSON Schema:

```text
evaluation/schemas/candidate-metadata.schema.json
```

---

## Candidateに書かなくなった値

v2では次をcandidateごとに繰り返していました。

```text
decoder
artifact_contract
tokenizer.kind
features
```

v3では削除しました。

これらは、

```text
variants.<name>.profile
        ↓
config/asr-catalog.json.decoder_profiles
```

から導出します。

例えば、

```json
"profile": "tdt-v1"
```

だけで、

```text
decoder             tdt
artifact contract   tdt-multi-graph-v1
tokenizer kind      vocabulary
required roles      encoder/predictor/joint
multi_graph         true
```

が決まります。

---

## Candidateに残す必要がある値

次は中央化しません。

```text
artifact path
artifact SHA-256
artifact size
input/output tensor names
blank/bos/prompt token IDs
TDT predictor state names/shapes/dtypes
KV-cache input/output names
processor/tokenizer path
```

これらはexportしたartifactごとに異なるためです。

---

# Parakeet: CTC + TDTを1 candidateに保持

推奨tree:

```text
candidates/parakeet-candidate-000002/
├── README.md
├── metadata.json
├── tokenizer/
│   └── vocabulary.json
├── ctc/
│   └── model.onnx
└── tdt/
    ├── encoder.onnx
    ├── predictor.onnx
    └── joint.onnx
```

例:

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
          "size_bytes": 123456789
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
          "size_bytes": 100
        },
        "predictor": {
          "path": "tdt/predictor.onnx",
          "sha256": "<PREDICTOR_SHA256>",
          "size_bytes": 100
        },
        "joint": {
          "path": "tdt/joint.onnx",
          "sha256": "<JOINT_SHA256>",
          "size_bytes": 100
        }
      },
      "bindings": {
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
        "path": "tokenizer/vocabulary.json"
      }
    }
  }
}
```

この1ファイルを変更せず、

```text
runtime_variant=ctc
runtime_variant=tdt
```

で使い分けます。

---

## TDT joint output

### separate

```json
{
  "token_output": "token_logits",
  "duration_output": "duration_logits",
  "output_mode": "separate"
}
```

### concatenated

```json
{
  "token_output": "joint_logits",
  "token_vocab_size": 1025,
  "output_mode": "concatenated"
}
```

この違いは実graph bindingなのでcandidateに残します。

---

# Whisper

Profile set:

```text
whisper-autoregressive-v1
```

variant:

```text
whisper
```

推奨tree:

```text
candidates/whisper-candidate-000003/
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
  "schema_version": 3,
  "candidate_id": "whisper-candidate-000003",
  "profile_set": "whisper-autoregressive-v1",
  "variants": {
    "whisper": {
      "profile": "whisper-autoregressive-v1",
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
          "sha256": "<WITH_PAST_SHA256>",
          "size_bytes": 100
        }
      },
      "bindings": {
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
        "path": "tokenizer"
      }
    }
  }
}
```

`tokenizer.kind = transformers_processor`はprofileから導出されるためcandidateには書きません。

---

## Runtime選択

Python CLI:

```bash
python -m parakeet_onnx.cli.evaluate \
  --runtime-variant tdt \
  --candidate-dir .ci/candidate \
  ...
```

環境変数:

```bash
ASR_RUNTIME_VARIANT=tdt
```

GitHub Actionsでは`runtime_variant` inputを使用します。

選択が省略された場合は、中央catalogのprofile set `default_variant`を使用します。

---

## Candidate identity

`CandidateArtifacts.bundle_sha256`は**選択されたvariant**の全artifactを、

```text
role
relative path
artifact SHA-256
```

でhashした値です。

したがって同じcandidate IDでも、

```text
ctc variant bundle SHA
tdt variant bundle SHA
```

は別identityです。

run-contextには選択された、

```text
profile_set
variant
profile
catalog fingerprint
variant bundle SHA
```

をsnapshotします。

---

## Publish

```bash
bash scripts/hf/hf-push-candidate.sh <candidate-directory>
```

manual prefixは受け付けません。

処理順:

```text
metadata schema-v3確認
    ↓
全variantを中央catalogで解決
    ↓
全variant runtime contract検証
    ↓
profile_setからcandidate_prefix_keyを取得
    ↓
Central Allocatorで採番
    ↓
candidate_idを書き込み
    ↓
再検証
    ↓
Bucketへpublish
```

新しいcandidateではschema v1/v2を生成しません。旧形式は既存artifactを読むための互換層です。
