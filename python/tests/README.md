# Python tests

Python tests verify producer-side contracts and source-framework-independent behavior.

## Unit scope

- config/catalog/revision resolution
- dataset manifest/materialization contracts
- audio decode/resample/frontend helpers
- candidate metadata generation
- NeMo reference typed contract
- NeMo reference normalization (`asr_metrics_v1` mirror)
- NeMo sample-set identity digest
- evaluation JSON Schema registry

NeMo itself is intentionally not imported by normal unit tests. Real `.nemo` restore, decoding, export, and transcription belong to HF Jobs/NeMo-container E2E.

## Quality authority

Python unit tests do not establish NeMo↔ONNX ASR quality acceptance. The authoritative quality path is the release Rust CLI:

```text
asr-eval nemo-onnx-quality
```

Python generates transcript/provenance evidence; Rust recomputes CER/WER for both sides with the same implementation.

## Commands

```bash
uv run pytest python/tests
uv run ruff check python/src python/tests scripts
```
