# Fixture generation completion

`fixture-generation-and-inspection` is the reviewed dispatch entrypoint. It
does not invent an HF run identifier and its plan/dispatch receipt is not
completion evidence. After the canonical Candidate Package Evaluate V2 run
has completed, invoke `fixture-generation-completion` with the evaluation run
identity. The workflow downloads the canonical `candidate-completion-*`
artifact and creates `fixture-completion-binding.json`.

The binding is accepted only when the candidate receipt is successful,
non-dry-run, matches the supplied evaluation run, and its `result_uri` belongs
to the requested Bucket. `bucket_run_identity` is derived from that URI; it is
not a second or independently generated Bucket ID. The candidate receipt SHA,
ACK run ID, result URI, and binding artifact form the auditable completion
chain.

The binding workflow is intentionally separate from dispatch so a queued or
failed HF Job cannot be represented as completed. Bucket synchronization is
upload-only and is never performed by this binding workflow.
