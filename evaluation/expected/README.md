# Expected Evaluation Results

This directory contains small, Git-tracked expected results used to verify
the evaluation pipeline itself.

It is intentionally different from the canonical reference artifacts stored
in the Hugging Face Bucket.

## Responsibilities

Files in this directory are used for fast deterministic checks such as:

- manifest resolution correctness
- dataset sample identity stability
- text normalization correctness
- decoder correctness
- tokenizer correctness
- result serialization correctness
- smoke-test regression detection

They are not intended to store complete model-reference outputs.

## Source of truth hierarchy

The project separates expected values into three layers.

### 1. Git-tracked expected values

Location:

```text
evaluation/expected/
