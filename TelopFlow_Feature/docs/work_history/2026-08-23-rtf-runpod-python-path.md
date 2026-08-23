# Work history: RunPod Python executable boundary

## Observation

After the SSH environment transfer was corrected, the guarded RTX 4090 Pod
reached the remote entrypoint but stopped with:

```text
/opt/rtf-benchmark/entrypoint.sh: line 116: python: command not found
```

The Pod was deleted by the safety wrapper. No content or metrics artifact was
accepted.

## Root cause

The HF Jobs launcher and RunPod SSH session exposed different PATH values for
the same image. The entrypoint used the unqualified `python` command for all
Python modules, so the RunPod SSH shell could not locate the interpreter.

## Fix

The entrypoint now resolves one interpreter at runtime in this order:

1. `python` from PATH;
2. `python3` from PATH;
3. known standard virtualenv/Conda/system paths.

All benchmark module invocations use the resolved executable. GHCR image
verification uses the same resolution logic rather than assuming an entrypoint
named `python`.

## Required next boundary

The fix must be included in a newly built and digest-pinned GHCR image. Do not
retry RunPod with the previous digest: its runtime contract is already proven
to lack the required Python command. After the new image is published, run one
RTX 4090 or other currently available GPU guarded batch 1 and require SSH,
fixture loading, content probe, completed receipt, and metrics/result identity
before any larger batch.
