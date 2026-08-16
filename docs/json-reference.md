# JSON Reference

この文書は、現行pipelineで扱う主要JSON/JSONLについて、**所有者・配置場所・編集可否・標準形**をまとめます。

例中のhash・revision・run IDは説明用です。実運用ではscript/runtimeが実値を生成します。

---

## 1. `config/asr-catalog.json`

**分類:** source-controlled

**所有者:** repository

**編集:** runtime semanticsを変更するPRでのみ編集

```json
{
  "schema_version": 1,
  "catalog_id": "asr-runtime-catalog-v1",
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
    },
    "whisper-autoregressive-v1": {
      "decoder": "whisper_autoregressive",
      "artifact_contract": "whisper-autoregressive-v1",
      "tokenizer_kind": "transformers_processor",
      "required_artifact_roles": ["encoder", "decoder"],
      "optional_artifact_roles": ["decoder_with_past"],
      "features": {
        "kv_cache": true,
        "multi_graph": true,
        "transformers_processor": true,
        "external_frontend": true,
        "timestamps": false
      }
    }
  },
  "profile_sets": {
    "parakeet-tdt-ctc-v1": {
      "variants": {
        "ctc": "ctc-v1",
        "tdt": "tdt-v1"
      },
      "default_variant": "ctc"
    },
    "whisper-autoregressive-v1": {
      "variants": {
        "whisper": "whisper-autoregressive-v1"
      },
      "default_variant": "whisper"
    }
  }
}
```

`runtime.json` はこのcatalogの `catalog_id` とcanonical SHA-256をpinします。

---

## 2. `config/hf-allocation-catalog.json`

**分類:** source-controlled

**所有者:** repository

**編集:** ID naming policy変更時のみ

```json
{
  "schema_version": 1,
  "catalog_id": "hf-allocation-catalog-v1",
  "prefixes": {
    "candidate.default": "candidate",
    "candidate.parakeet-tdt-ctc-v1": "parakeet-candidate",
    "candidate.whisper-autoregressive-v1": "whisper-candidate",
    "experiment.cpu_full": "cpu-full-eval",
    "experiment.cross_platform_parity": "cross-platform-parity",
    "experiment.rust_eval": "rust-eval",
    "config.version": "config"
  }
}
```

6桁sequence suffixはここへ書きません。中央AllocatorがBucket全体を走査して採番します。

---

## 3. Candidate `metadata.json`

**分類:** human-authored

**配置:** local candidateおよび `candidates/<candidate-id>/metadata.json`

**編集:** publish前のみ

### Parakeet CTC + TDT

```json
{
  "profile_set": "parakeet-tdt-ctc-v1",
  "variants": {
    "ctc": {
      "artifacts": {
        "primary": "ctc/model.onnx"
      },
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

### Whisper

```json
{
  "profile_set": "whisper-autoregressive-v1",
  "variants": {
    "whisper": {
      "artifacts": {
        "encoder": "encoder.onnx",
        "decoder": "decoder.onnx",
        "decoder_with_past": "decoder_with_past.onnx"
      },
      "tokenizer": "tokenizer"
    }
  }
}
```

書いてはいけないもの:

- `candidate_id`
- `schema_version`
- hash / size
- catalog fingerprint
- decoder / profile
- graph binding
- blank/BOS/duration
- state/KV information

---

## 4. `reference.json`

**分類:** human-authored revision lock

**配置:** `config/versions/config-NNNNNN/reference.json`

```json
{
  "schema_version": 1,
  "development_artifact": {
    "repo_id": "gawohok7/jpapt-v2.2-dev",
    "revision": "4f7d0f535f4f05c9721af7d9b3064b7caeecf001"
  },
  "upstream": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision": "6b8d6f42f4a8dbca38d90b60f8dc727f7692699f"
  },
  "tokenizer": {
    "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "revision": "6b8d6f42f4a8dbca38d90b60f8dc727f7692699f"
  },
  "reference": {
    "id": "nemo-reference-v1",
    "revision": "3bd6d9ca347ad68f85e788cc34c2c22f116c4c91",
    "canonical_framework": "nemo"
  }
}
```

Whisperでは `canonical_framework` を `transformers` とし、upstream/tokenizerをKotoba Whisper revisionへpinします。

`decoder` / `decoders` は書きません。

---

## 5. `evaluation-schema.json`

**分類:** human-authored revision lock

**配置:** `config/versions/config-NNNNNN/evaluation-schema.json`

```json
{
  "schema_version": 1,
  "schema": {
    "id": "asr-evaluation-v1",
    "revision": "8e45d2174cb77fd0c2bb3f927776bc9d03df50f8"
  }
}
```

このdocumentは評価schema identityをpinします。decoder semanticsは書きません。

---

## 6. `datasets-lock.json`

**分類:** human-authored revision lock

**配置:** `config/versions/config-NNNNNN/datasets-lock.json`

標準評価datasetとして `japanese-asr/ja_asr.jsut_basic5000` を使う例:

```json
{
  "schema_version": 1,
  "datasets": [
    {
      "id": "jsut-basic5000",
      "repo_id": "japanese-asr/ja_asr.jsut_basic5000",
      "revision": "7e75d6c3b96c2348d4ef43a9e5fce742e4ed0131",
      "subset": "default",
      "split": "test",
      "sha256": "1f1c26f32adf67114734a7a47619a3669fdc8f9a6aa3e32796bb83d3cf314967",
      "manifest": "evaluation/manifests/jsut-basic5000.jsonl"
    }
  ]
}
```

loaderでは `subset` / `split` / `sha256` / `manifest` 自体はoptionalですが、**execution snapshot生成時には `sha256` と `manifest` が必須**です。標準運用では最初から完全形で書いてください。

---

## 7. `runtime.json`

**分類:** generated

**生成:** Rust `asr-config-publish prepare`（`hf-push-config-version.sh` から呼び出し）

**配置:** `config/versions/config-NNNNNN/runtime.json`

Parakeet例:

```json
{
  "schema_version": 1,
  "catalog": {
    "id": "asr-runtime-catalog-v1",
    "sha256": "0db04194ec2e5d32fb2ae66f00ed3cb351b6183e8dfc747c779659eebd5a1b4e"
  },
  "profile_set": "parakeet-tdt-ctc-v1"
}
```

Whisper例:

```json
{
  "schema_version": 1,
  "catalog": {
    "id": "asr-runtime-catalog-v1",
    "sha256": "0db04194ec2e5d32fb2ae66f00ed3cb351b6183e8dfc747c779659eebd5a1b4e"
  },
  "profile_set": "whisper-autoregressive-v1"
}
```

このファイルを手書きしてcatalog hashを合わせる運用はしません。

---

## 8. `config/current.json`

**分類:** generated mutable pointer

**配置:** Bucket `config/current.json`

```json
{
  "schema_version": 1,
  "config_version": "config-000123",
  "bundle_sha256": "6c1302cc2e65f6baa264fc37c44ca8a68c4de0a78d20fc402b6c3856b42508b2",
  "updated_at": "2026-08-16T12:00:00+00:00"
}
```

`hf-push-config-version.sh` が新version publish後に更新します。

---

## 9. Local `resolved.json`

**分類:** generated local selection snapshot

**配置:** `.ci/hf/config/resolved.json`

```json
{
  "schema_version": 1,
  "config_version": "config-000123",
  "current_version": "config-000123",
  "selection_source": "current"
}
```

`HF_CONFIG_VERSION=config-000120` などでoverrideした場合:

```json
{
  "schema_version": 1,
  "config_version": "config-000120",
  "current_version": "config-000123",
  "selection_source": "override"
}
```

`revisions/` の隣に存在し、revision bundleへconcrete config identityを与えます。

---

## 10. Generated candidate contract

**分類:** generated execution contract

**生成:** `CandidateArtifacts.load()` + inspection

通常はCI用temporary JSONや `run-context.json.metadata.candidate` として現れます。

CTC例:

```json
{
  "schema_version": 1,
  "candidate_root": "/work/candidate",
  "candidate_id": "parakeet-candidate-000124",
  "profile_set": "parakeet-tdt-ctc-v1",
  "variant": "ctc",
  "profile": "ctc-v1",
  "decoder": "ctc",
  "artifact_contract": "ctc-single-graph-v1",
  "catalog": {
    "id": "asr-runtime-catalog-v1",
    "sha256": "0db04194ec2e5d32fb2ae66f00ed3cb351b6183e8dfc747c779659eebd5a1b4e"
  },
  "bundle_sha256": "2b8648cd6851f205497c0e0fc06f52ce8f52f9cd31f233fc1a2bf46f49d8a133",
  "artifacts": {
    "primary": {
      "path": "ctc/model.onnx",
      "sha256": "76f97f39bc9290c79b95ae59e8a30f86d25c73fc6d4053903fca01b43dd9ff2f",
      "size_bytes": 625147392
    }
  },
  "tokenizer": {
    "kind": "vocabulary",
    "path": "tokenizer/vocabulary.json"
  },
  "features": {
    "kv_cache": false,
    "multi_graph": false,
    "transformers_processor": false,
    "external_frontend": false,
    "timestamps": false
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
  }
}
```

artifact hash/size、binding、blank IDを人が編集しません。

---

## 11. `run-context.json`

**分類:** generated immutable execution snapshot

**schema:** `evaluation/schemas/run-context.schema.json`, version 2

**配置:** `runs/<run-id>/run-context.json`

以下はCTC/CPUの縮約しない標準例です。

```json
{
  "schema_version": 2,
  "run_id": "20260816T120000Z-parakeet-tdt-ctc-0.6b-ja-linux-cpu-full-2b8648cd-a1b2c3d4",
  "created_at": "2026-08-16T12:00:00+00:00",
  "config_identity": "parakeet-tdt_ctc-0.6b-ja:linux:cpu:full",
  "model_id": "parakeet-tdt_ctc-0.6b-ja",
  "environment_id": "linux",
  "provider_id": "cpu",
  "evaluation_id": "full",
  "artifact": {
    "path": ".ci/hf/candidate/ctc/model.onnx",
    "sha256": "76f97f39bc9290c79b95ae59e8a30f86d25c73fc6d4053903fca01b43dd9ff2f",
    "size_bytes": 625147392,
    "candidate_id": "parakeet-candidate-000124",
    "artifact_role": "primary"
  },
  "git": {
    "repository": "bie3yeik-lgtm/jpapt-v2.2-inspection",
    "commit": "eac07000e87d4c26a0d8add16551fa6ae8b2db3a",
    "ref": "refs/heads/agent/provider-strict-probes",
    "dirty": false
  },
  "host": {
    "os": "Linux",
    "architecture": "x86_64",
    "hostname": "github-runner",
    "python_version": "3.12.13",
    "implementation": "CPython",
    "is_wsl": false,
    "github_runner_os": "Linux",
    "github_runner_arch": "X64",
    "github_run_id": "31944684170",
    "github_run_attempt": "1"
  },
  "runtime": {
    "implementation": "python",
    "backend": "onnxruntime",
    "backend_version": "1.28.0",
    "provider_id": "cpu",
    "provider_ort_name": "CPUExecutionProvider",
    "provider_available": true
  },
  "revisions": {
    "config_version": "config-000123",
    "bundle_sha256": "6c1302cc2e65f6baa264fc37c44ca8a68c4de0a78d20fc402b6c3856b42508b2",
    "runtime": {
      "document_sha256": "876a5b77e3453e97cb386ffbbd1c132ab1326829b654ba276b74fb8cd814f6a9",
      "catalog": {
        "id": "asr-runtime-catalog-v1",
        "sha256": "0db04194ec2e5d32fb2ae66f00ed3cb351b6183e8dfc747c779659eebd5a1b4e"
      },
      "profile_set": "parakeet-tdt-ctc-v1"
    },
    "reference": {
      "document_sha256": "3f27bb9ac980ceda76e9416005869254c9bcda3d55b0433505289be8ef273550",
      "development_artifact": {
        "repo_id": "gawohok7/jpapt-v2.2-dev",
        "revision": "4f7d0f535f4f05c9721af7d9b3064b7caeecf001"
      },
      "upstream": {
        "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
        "revision": "6b8d6f42f4a8dbca38d90b60f8dc727f7692699f"
      },
      "tokenizer": {
        "repo_id": "nvidia/parakeet-tdt_ctc-0.6b-ja",
        "revision": "6b8d6f42f4a8dbca38d90b60f8dc727f7692699f"
      },
      "reference_id": "nemo-reference-v1",
      "reference_revision": "3bd6d9ca347ad68f85e788cc34c2c22f116c4c91",
      "canonical_framework": "nemo"
    },
    "evaluation_schema": {
      "document_sha256": "d4e0b9b00ec0c57d3dad99480630106b7f38e6a6fdf27444b5bcc93f771a97e2",
      "schema_id": "asr-evaluation-v1",
      "schema_revision": "8e45d2174cb77fd0c2bb3f927776bc9d03df50f8"
    },
    "datasets": {
      "document_sha256": "70fe05a1ad77fa828afab253e711b13345c17cc48997ad144382617e74d13c68",
      "entries": [
        {
          "id": "jsut-basic5000",
          "repo_id": "japanese-asr/ja_asr.jsut_basic5000",
          "revision": "7e75d6c3b96c2348d4ef43a9e5fce742e4ed0131",
          "subset": "default",
          "split": "test",
          "sha256": "1f1c26f32adf67114734a7a47619a3669fdc8f9a6aa3e32796bb83d3cf314967",
          "manifest": "evaluation/manifests/jsut-basic5000.jsonl"
        }
      ]
    }
  },
  "config": {
    "identity": "parakeet-tdt_ctc-0.6b-ja:linux:cpu:full",
    "sources": {
      "model": "config/models/parakeet-tdt_ctc-0.6b-ja.toml",
      "provider": "config/providers/cpu.toml",
      "environment": "config/environments/linux.toml",
      "evaluation": "config/evaluation/full.toml"
    },
    "resolved": {
      "model": {},
      "provider": {},
      "environment": {},
      "evaluation": {},
      "resolved": {
        "model_id": "parakeet-tdt_ctc-0.6b-ja",
        "provider_id": "cpu",
        "environment_id": "linux",
        "evaluation_id": "full"
      }
    }
  },
  "metadata": {
    "candidate": {
      "schema_version": 1,
      "candidate_root": "/work/candidate",
      "candidate_id": "parakeet-candidate-000124",
      "profile_set": "parakeet-tdt-ctc-v1",
      "variant": "ctc",
      "profile": "ctc-v1",
      "decoder": "ctc",
      "artifact_contract": "ctc-single-graph-v1",
      "catalog": {
        "id": "asr-runtime-catalog-v1",
        "sha256": "0db04194ec2e5d32fb2ae66f00ed3cb351b6183e8dfc747c779659eebd5a1b4e"
      },
      "bundle_sha256": "2b8648cd6851f205497c0e0fc06f52ce8f52f9cd31f233fc1a2bf46f49d8a133",
      "artifacts": {
        "primary": {
          "path": "ctc/model.onnx",
          "sha256": "76f97f39bc9290c79b95ae59e8a30f86d25c73fc6d4053903fca01b43dd9ff2f",
          "size_bytes": 625147392
        }
      },
      "tokenizer": {
        "kind": "vocabulary",
        "path": "tokenizer/vocabulary.json"
      },
      "features": {
        "kv_cache": false,
        "multi_graph": false,
        "transformers_processor": false,
        "external_frontend": false,
        "timestamps": false
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
      }
    },
    "runtime_variant": "ctc",
    "runtime_profile": "ctc-v1"
  }
}
```

実際の `config.resolved` にはTOMLのresolved内容全体が入るため、上例の空object部分は説明上の省略です。

---

## 12. `metrics.json`

**分類:** generated benchmark result

**schema:** `evaluation/schemas/benchmark.schema.json`

**配置:** `runs/<run-id>/metrics.json` および `benchmarks/.../<run-id>.json`

標準的な形:

```json
{
  "schema_version": 1,
  "run_id": "20260816T120000Z-parakeet-tdt-ctc-0.6b-ja-linux-cpu-full-2b8648cd-a1b2c3d4",
  "candidate": {
    "candidate_id": "parakeet-candidate-000124",
    "model_id": "parakeet-tdt_ctc-0.6b-ja",
    "artifact_sha256": "2b8648cd6851f205497c0e0fc06f52ce8f52f9cd31f233fc1a2bf46f49d8a133",
    "artifact_size_bytes": 625147392,
    "decoder": "ctc"
  },
  "evaluation": {
    "suite": "full",
    "manifest": "evaluation/manifests/jsut-basic5000.jsonl",
    "expected_sample_count": 768,
    "reference_revision_sha256": "3f27bb9ac980ceda76e9416005869254c9bcda3d55b0433505289be8ef273550",
    "evaluation_schema_sha256": "d4e0b9b00ec0c57d3dad99480630106b7f38e6a6fdf27444b5bcc93f771a97e2",
    "datasets_lock_sha256": "70fe05a1ad77fa828afab253e711b13345c17cc48997ad144382617e74d13c68",
    "revision_bundle_sha256": "6c1302cc2e65f6baa264fc37c44ca8a68c4de0a78d20fc402b6c3856b42508b2"
  },
  "runtime": {
    "implementation": "python",
    "backend": "onnxruntime",
    "backend_version": "1.28.0",
    "environment_id": "linux",
    "provider_id": "cpu",
    "provider_ort_name": "CPUExecutionProvider",
    "os": "Linux",
    "architecture": "x86_64"
  },
  "samples": {
    "expected": 768,
    "attempted": 768,
    "successful": 768,
    "failed": 0,
    "skipped": 0,
    "total_audio_duration_sec": 5421.4
  },
  "quality": {
    "cer": 0.041,
    "wer": 0.118
  },
  "performance": {
    "load_ms": 410.3,
    "session_creation_ms": 388.5,
    "total_processing_ms": 192403.0,
    "rtf": 0.0355,
    "per_sample": {
      "mean_ms": 250.5,
      "median_ms": 220.0,
      "p50_ms": 220.0,
      "p95_ms": 480.0,
      "p99_ms": 620.0,
      "min_ms": 75.0,
      "max_ms": 831.0
    },
    "components": {
      "audio_decode_ms": 18.0,
      "resample_ms": 5.2,
      "frontend_ms": 0.0,
      "encoder_ms": 190.0,
      "decoder_ms": 0.0,
      "postprocess_ms": 1.5,
      "inference_ms": 190.0
    }
  },
  "memory": {
    "peak_ram_mb": 2140.0,
    "peak_device_memory_mb": null
  },
  "parity": {
    "reference_run_id": null,
    "text_matches": 0,
    "text_mismatches": 0,
    "token_matches": 0,
    "token_mismatches": 0,
    "text_match_rate": null,
    "token_match_rate": null,
    "numeric": {
      "frontend": {
        "compared_samples": 0,
        "failed_samples": 0,
        "max_abs_error": null,
        "max_mean_abs_error": null,
        "max_relative_l2": null
      },
      "encoder": {
        "compared_samples": 0,
        "failed_samples": 0,
        "max_abs_error": null,
        "max_mean_abs_error": null,
        "max_relative_l2": null
      },
      "logits": {
        "compared_samples": 0,
        "failed_samples": 0,
        "max_abs_error": null,
        "max_mean_abs_error": null,
        "max_relative_l2": null
      }
    }
  },
  "provider": {
    "requested": "cpu",
    "registered": true,
    "execution_proven": true,
    "fallback_detected": false,
    "fallback_only": false,
    "assigned_nodes": null,
    "fallback_nodes": null
  },
  "acceptance": {
    "passed": true,
    "quality_passed": true,
    "parity_passed": null,
    "provider_passed": true,
    "performance_passed": true,
    "failed_checks": [],
    "warnings": []
  },
  "errors": {
    "total": 0,
    "fatal": 0,
    "by_code": {}
  }
}
```

`null` は「未観測/非適用」を表し、0やfalseで代用しません。

---

## 13. `promotion.json`

**分類:** generated promotion record

**配置:** Model Repo `release/promotion.json` および Bucket `runs/<run-id>/promotion.json`

```json
{
  "schema_version": 3,
  "candidate_id": "parakeet-candidate-000124",
  "runtime_variant": "ctc",
  "validated_run_id": "20260816T120000Z-parakeet-tdt-ctc-0.6b-ja-linux-cpu-full-2b8648cd-a1b2c3d4",
  "model_id": "parakeet-tdt_ctc-0.6b-ja",
  "candidate_sha256": "2b8648cd6851f205497c0e0fc06f52ce8f52f9cd31f233fc1a2bf46f49d8a133",
  "candidate_identity_kind": "variant_bundle",
  "revision_bundle_sha256": "6c1302cc2e65f6baa264fc37c44ca8a68c4de0a78d20fc402b6c3856b42508b2",
  "evaluation_id": "full",
  "provider_id": "cpu",
  "promoted_at": "2026-08-16T13:00:00+00:00",
  "source": {
    "type": "hf_bucket_candidate",
    "bucket": "gawohok7/jpapt-v2.2-dev-bucket",
    "candidate_path": "candidates/parakeet-candidate-000124"
  },
  "destination": {
    "type": "hf_model_repo",
    "repo_id": "gawohok7/jpapt-v2.2-dev"
  }
}
```

このrecordはpromotion scriptが生成します。

---

## 14. Evaluation manifest JSONL

**分類:** source-controlled evaluation input

manifestは `.json` ではなく `.jsonl` です。現在のminimal形式では1行がselection requestです。

```json
{"dataset_id":"jsut-basic5000","count":12,"seed":"smoke-jsut-v1"}
```

長さ制約を付ける場合:

```json
{"dataset_id":"jsut-basic5000","count":12,"seed":"smoke-jsut-v1","min_duration_sec":1.0,"max_duration_sec":15.0}
```

`min_duration_sec` はinclusive、`max_duration_sec` はexclusiveです。

---

## 15. `samples.jsonl` の1行

**分類:** generated per-sample evidence

**schema:** `evaluation/schemas/result.schema.json`

```json
{"schema_version":1,"run_id":"run-1","sample":{"id":"jsut-basic5000:000123","dataset_id":"jsut-basic5000","dataset_repo_id":"japanese-asr/ja_asr.jsut_basic5000","dataset_revision":"7e75d6c3b96c2348d4ef43a9e5fce742e4ed0131","subset":"default","split":"test","index":123,"audio_sha256":"8f9aa6d1e29e6c50511626ba6db3f3fa55d218e282055972068310d6639c4f2a","audio_duration_sec":7.42,"sample_rate_hz":16000,"reference_text":"これはテスト音声です"},"execution":{"runtime":"python","backend":"onnxruntime","provider_id":"cpu","decoder":"ctc","batch_size":1},"output":{"text":"これはテスト音声です","normalized_text":"これはテスト音声です","tokens":[12,34,56],"token_count":3},"quality":{"cer":0.0,"wer":0.0},"timing":{"load_ms":null,"session_creation_ms":null,"audio_decode_ms":8.0,"resample_ms":2.0,"frontend_ms":0.0,"encoder_ms":180.0,"decoder_ms":0.0,"postprocess_ms":1.0,"inference_ms":180.0,"total_ms":191.0,"rtf":0.0257},"memory":{"peak_ram_mb":null,"peak_device_memory_mb":null},"parity":{"reference_run_id":null,"text_match":null,"token_match":null,"numeric":{"frontend":{"compared":false,"passed":null,"max_abs_error":null,"mean_abs_error":null,"relative_l2":null},"encoder":{"compared":false,"passed":null,"max_abs_error":null,"mean_abs_error":null,"relative_l2":null},"logits":{"compared":false,"passed":null,"max_abs_error":null,"mean_abs_error":null,"relative_l2":null}}},"provider":{"requested":"cpu","registered":true,"used":true,"fallback_detected":false,"fallback_only":false,"assigned_nodes":null,"fallback_nodes":null},"status":"success","errors":[]}
```

---

## 16. 何を手で書くか

通常、人が用意するJSONは次に限定します。

```text
candidate metadata.json
reference.json
evaluation-schema.json
datasets-lock.json
```

repository-level catalog変更を行う場合のみ:

```text
config/asr-catalog.json
config/hf-allocation-catalog.json
```

次は必ず生成物として扱います。

```text
runtime.json
config/current.json
resolved.json
generated candidate contract
run-context.json
metrics.json
samples.jsonl
promotion.json
```
