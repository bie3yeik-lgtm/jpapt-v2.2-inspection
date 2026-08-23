# RTF RunPod balance gate

Date: 2026-08-23
Scope: local provider adapter and guarded RunPod execution

## Evidence

- Run ID: `rtf-runpod-guarded-20260823`
- Provider: RunPod
- Requested route: one guarded RTX 3090 job
- Result: blocked before Pod creation
- Provider message: account balance is too low to rent a Pod
- Pod ID: none
- Charge: none observed

The attempt did not reach image pull, SSH readiness, dataset transfer, model
load, or inference. It is therefore not evidence of a RunPod runtime failure.
The next real RunPod attempt must wait until the account is funded; repeated
retries are prohibited to avoid pointless API calls and cost.

## Contract change

`scripts/run-benchmark.sh` now classifies the provider response as
`RUNPOD_ACCOUNT_BALANCE_TOO_LOW`, rather than the generic
`PROVIDER_RUNPOD_POD_CREATE_FAILED`. The receipt remains `blocked` and does
not claim that benchmark execution started.

The local provider mock reproduces this response and verifies the typed
receipt without creating a Pod. This is the acceptance evidence available
without additional RunPod spend.

## Acceptance record

- Authority: RunPod API response captured by the guarded attempt; repository
  adapter contract for the typed classification.
- Changed scope: RunPod create failure classification and mock coverage only.
- Unverified: successful RunPod execution after funding.
- Rollback: remove the classification branch and its mock case; no existing
  result artifact is modified.
- Next safe unit: run the local static/mock adapter checks; after funding,
  perform exactly one guarded RunPod smoke run before any full matrix.
