# Candidate Metadata v3 / Runtime Variant

## 目的

`candidates/<candidate-id>/metadata.json` はcandidate固有のartifact identityとruntime bindingの正本です。

再利用可能なdecoder semanticsはcandidateへ複製しません。

```text
Runtime semantics
    config/asr-catalog.json

Candidate-specific facts
    candidates/<candidate-id>/metadata.json
```

詳細な配置原則は [`json-contract-design.md`](./json-contract-design.md) を参照してください。

---

## Canonical schema v3

新規candidateは次の5項目をtop-level requiredとします。

```text
schema_version
candidate_id
catalog
profile_set
variants
```

最小形:

```json
{
  "schema_version": 3,
  "candidate_id": "parakeet-candidate-000002",
  "catalog": {
    "id": "asr-runtime-catalog-v1",
    "sha256": "<ASR_RUNTIME_CATALOG_SHA256>"
  },
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
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

## `catalog`

candidateは利用したASR runtime catalog snapshotをpinします。

```json
"catalog": {
  "id": "asr-runtime-catalog-v1",
  "sha256": "<ASR_RUNTIME_CATALOG_SHA256>"
}
```

`CandidateArtifacts`はcheckout中の`config/asr-catalog.json`とこのfingerprintが一致しなければschema-v3 candidateを拒否します。

これにより、同じ`profile_set`名の意味が将来変更されても過去candidateの意味がsilentに変化しません。

---

## profileをvariantごとに書かない理由

次は冗長なので削除しました。

```json
"ctc": {
  "profile": "ctc-v1"
}
```

profile IDは、

```text
profile_set = parakeet-tdt-ctc-v1
variant = ctc
        ↓
config/asr-catalog.json
        ↓
ctc-v1
```

と一意に決定できます。

したがってcandidateに必要なのはvariant名だけです。

---

## Candidateに書かない値

以下は中央runtime catalogから導出します。

```text
decoder
artifact_contract
profile ID
tokenizer kind
required/optional artifact roles
features
```

例えば`parakeet-tdt-ctc-v1 + tdt`から、

```text
profile              tdt-v1
decoder              tdt
artifact contract    tdt-multi-graph-v1
tokenizer kind       vocabulary
required roles       encoder / predictor / joint
multi_graph          true
```

が決まります。

---

## Candidateに残す値

以下は実artifact/exportごとに異なるため中央化しません。

```text
artifact path
artifact SHA-256
artifact size
input/output tensor names
blank/bos/eos/prompt token IDs
TDT durations
predictor state names/shapes/dtypes
KV-cache input/output names
processor/tokenizer asset path
```

`bindings.decoder_config`はdecoder一般のpolicyではなく、そのcandidateを動かすためのmodel/export固有bindingです。

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

完全例:

```json
{
  "schema_version": 3,
  "candidate_id": "parakeet-candidate-000002",
  "catalog": {
    "id": "asr-runtime-catalog-v1",
    "sha256": "<ASR_RUNTIME_CATALOG_SHA256>"
  },
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
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

このJSONを書き換えずに、

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

これは実graphのI/O bindingなのでcandidateに残します。

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
  "catalog": {
    "id": "asr-runtime-catalog-v1",
    "sha256": "<ASR_RUNTIME_CATALOG_SHA256>"
  },
  "profile_set": "whisper-autoregressive-v1",
  "variants": {
    "whisper": {
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

`transformers_processor`というtokenizer kindやWhisperのfeature要求はprofileから導出します。

---

## Runtime選択

CLI:

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

GitHub Actionsでは`runtime_variant` inputを使用します。省略時はprofile setの`default_variant`です。

---

## Candidate identity

`CandidateArtifacts.bundle_sha256`は**選択されたvariant**のartifact集合を、

```text
role
relative path
artifact SHA-256
```

でhashします。

したがって同じcandidate IDでもCTC/TDTは別runtime artifact identityを持ちます。

run-contextのcandidate provenanceには、

```text
catalog fingerprint
profile_set
variant
resolved profile
decoder
artifact contract
variant bundle SHA
```

をsnapshotします。

---

## Publish

```bash
bash scripts/hf/hf-push-candidate.sh <candidate-directory>
```

manual prefixは指定しません。

```text
metadata schema-v3確認
    ↓
catalog fingerprint確認
    ↓
全variantをprofile_setから解決
    ↓
全variant runtime contract検証
    ↓
profile_setからallocation prefix key解決
    ↓
Central Allocatorで採番
    ↓
candidate_idを書き込み
    ↓
再検証
    ↓
Bucketへpublish
```

新規candidateはschema v3のみを生成します。schema v1/v2は過去artifact読み取り用です。
