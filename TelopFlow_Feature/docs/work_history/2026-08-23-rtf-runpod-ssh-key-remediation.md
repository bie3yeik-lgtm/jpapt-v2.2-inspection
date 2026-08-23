# Work history: RTF RunPod SSH key boundary

## Objective

Restore the RunPod SSH boundary for the RTF benchmark image without changing
the benchmark payload, provider credentials, or canonical fixture.

## Scope and authority

- Authority: local repository contract plus the guarded HF/RunPod provider
  observations recorded in `docs/rtf-provider-failure-remediation-20260821.md`.
- Changed scope: benchmark image entrypoint, provider adapter static checks, and
  this work-history record.
- Out of scope: model or dataset revision changes, GHCR publication, provider
  result acceptance, and GitHub Actions secret changes.

## Evidence

### HF guarded run

The immutable smoke run completed content probing and 21/21 transcriptions.
The job emitted completed content and metrics receipts. This confirms the HF
adapter and the current content/data-loader guard for batch 1, but does not
prove RunPod readiness.

### RunPod guarded run

The Pod was created and became `running`, but the SSH probe returned
`Permission denied (publickey,password)`. The Pod was deleted by the cleanup
path and no metrics/result were accepted. The account key fingerprint reported
by RunPod matched the local synchronized key, so the failure was attributed to
the custom image ENTRYPOINT replacing the base image startup that normally
materializes `PUBLIC_KEY` into `authorized_keys`.

### Local verification

- `rtf-local-preflight.sh --provider all`: PASS (no provider creation).
- `test-rtf-provider-adapters.sh --mode static`: PASS.
- `test-rtf-provider-adapters.sh --mode mock`: PASS, including typed provider
  failure receipts and cleanup behavior.
- Local Docker image build `parakeet-rtf-benchmark:ssh-key-test`: PASS.
- A local container with a non-secret test `PUBLIC_KEY` materialized
  `/root/.ssh/authorized_keys` and started `sshd`: PASS.
- The new image has not yet been published and therefore has not been retried
  on RunPod.

## Remediation

The keepalive path now creates `/root/.ssh`, writes the provider-injected
`PUBLIC_KEY` to `authorized_keys`, applies restrictive permissions, enables
public-key authentication, validates `sshd_config`, and starts `sshd`.

## Security note

The RunPod Pod creation environment can expose runtime environment values in
provider metadata. A prior diagnostic inspection exposed the HF credential in
that metadata. The credential value is intentionally not recorded here or in
logs; the user should rotate that HF token before any further live RunPod
execution and use the minimum required scope.

## Remaining safe unit

Publish the changed image through the repository GHCR workflow, capture its new
digest, and run exactly one guarded RunPod batch-1 retry. Do not reuse the old
image digest for acceptance.
