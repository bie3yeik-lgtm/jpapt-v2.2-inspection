# Python Tests

The canonical test root is:

```text
python/tests/
```

Structure:

```text
python/tests/
├── conftest.py
├── unit/
├── integration/
└── fixtures/
```

## Unit tests

Validate isolated contracts such as:

- repository path discovery
- manifest parsing
- stable-hash selection
- dataset dataclasses
- materialization
- audio decode
- canonical resampling
- feature adapters
- disposable dataset cache
- evaluation schema imports

## Integration tests

Validate important boundaries:

```text
DatasetRecord
    ↓
DatasetMaterializer
    ↓
local audio file
    ↓
decode
    ↓
CanonicalAudio
```

Network-dependent Hugging Face dataset tests are intentionally not part of the
default suite.

## Run

```bash
mise exec -- uv run pytest
```

or:

```bash
uv run pytest python/tests
```

## Philosophy

Tests must not silently download models or datasets.

Heavy NeMo and ONNX parity tests should be opt-in or CI-specific integration
tests once the corresponding implementation is stable.
