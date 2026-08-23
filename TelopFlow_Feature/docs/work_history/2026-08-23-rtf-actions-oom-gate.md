# Work history: RTF guarded batch OOM boundary

## External evidence

GitHub Actions run `32616009238` was dispatched with HF/t4, `smoke`, and
`guarded`. The GHCR image and Resolver prerequisites passed. The first batch
completed, but the workflow then launched a larger batch and received:

```text
BENCHMARK_INFERENCE_FAILED: CUDA out of memory. Tried to allocate 2.71 GiB
```

The next batch was represented as `COST_GUARD_SKIPPED`, and the overall
workflow conclusion was still `success` because at least one batch had
completed. This was insufficient as a minimum-cost guarded acceptance signal:
the failed larger batch had already consumed provider startup and inference
resources.

The corresponding local HF guarded run with batch 1 completed 21/21 samples
without OOM, using the loader policy `num_workers=0`, `pin_memory=false`, and
`use_lhotse=false`.

## Remediation

`rtf-benchmark-run.yml` now selects its batch list by cost mode:

- `guarded`: batch 1 only;
- `full-matrix`: batches 1, 8, and 32, with explicit expensive-matrix intent.

The benchmark execution, RunPod cleanup, and receipt normalization loops use
the same selected list, so guarded runs do not create synthetic receipts or
cleanup entries for unattempted larger batches.

## Acceptance boundary

`guarded` success proves only the smallest provider path and its content/result
contract. It does not claim that batch 8 or 32 fit the selected GPU. Those
cases require an explicit `full-matrix` run after GPU-specific memory sizing
and are not a prerequisite for the no-waste guarded smoke gate.

The first correction exposed one remaining post-processing defect: receipt
normalization still aggregated the old fixed `1,8,32` list and failed when the
unattempted guarded files were absent. The normalization aggregation now uses
the same selected `batch_sizes` array as execution and cleanup.

The corrected workflow was rerun as Actions run `32617045634` on HF/t4. It
completed successfully. Its uploaded artifact contains only
`results/batches/batch-1/result-receipt.json`; the receipt is `completed` and
has metrics SHA-256
`f2adf4c83f12ae133806d39622345045284ae326686420899f80c3084c5faf03`.
No batch-8 or batch-32 provider Job was created in this guarded run.

## Local evidence

- `test-rtf-provider-adapters.sh --mode static`: PASS.
- `test-rtf-provider-adapters.sh --mode mock`: PASS.
- YAML parse with PyYAML: PASS.
- `git diff --check`: PASS.
- Actions run `32617045634`: PASS, batch-1 only; no OOM.
- No new provider Job or Pod was created for this workflow edit.

## Next safe unit

Run the static/mock checks, commit and push this workflow correction, then
rerun one HF/t4 guarded Actions benchmark. Do not rerun full-matrix until the
guarded result is accepted.
