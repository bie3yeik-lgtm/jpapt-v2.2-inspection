# Work history: RunPod environment transfer quoting boundary

## Observation

The guarded RTX 4090 smoke reached `runtimeStatus=running` and passed the SSH
probe, but the remote entrypoint stopped with:

```text
/opt/rtf-benchmark/entrypoint.sh: line 76: RTF_DATASET_ID: RTF_DATASET_ID is required
```

The local adapter had generated `RTF_DATASET_ID`, but it was not present in the
SSH session. The Pod was deleted by the safety cleanup and no metrics/result
was accepted.

## Root cause

The adapter passed a compound command through the SSH command string:

```text
bash -lc "set -a; . /run/rtf-benchmark.env; set +a; ..."
```

The SSH wrapper reconstructs remote command arguments. The command reached the
remote shell with its quoting altered, so `bash -lc` executed only `set` and
the environment file was not reliably sourced. The visible shell variable
dump in the provider log is evidence of this parsing boundary.

## Fix

- transfer the allowlisted environment using `tee /run/rtf-benchmark.env` over
  SSH stdin;
- apply permissions with the simple remote command `chmod 600 ...`;
- invoke the benchmark using `bash -s` and send a short script over stdin;
- quote only the Pod ID with `printf %q` inside that script.

No token is placed in the RunPod control-plane create request. The environment
file remains allowlisted and mode 600.

## Acceptance evidence

- static adapter contract check passes;
- mock RunPod content/receipt collection passes;
- next guarded RunPod retry must show `RTF_DATASET_ID`-dependent fixture
  loading, `content_available=true`, and completed metrics/result receipts.

Do not start batch 8 or 32 until batch 1 is accepted.
