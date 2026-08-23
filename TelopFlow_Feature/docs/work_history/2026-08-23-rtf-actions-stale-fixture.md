# RTF Benchmark Run 32625835376: stale fixture failure and identity gate

## Summary

The first GitHub Actions RunPod execution after the successful GHCR publish
did not produce benchmark metrics. The RunPod pod was created with the
expected immutable image digest and was cleaned up, but the benchmark used an
outdated fixture revision. The provider then failed during the content probe
with an abstract `ASRModel` instantiation error.

This is recorded as a blocked execution, not as an RTF score.

## Observed execution

- Actions run: `32625835376`
- Provider: RunPod
- Profile: `smoke`
- Model revision:
  `44edb27eea9317daf89333e75eb830db4b1cc298`
- Published benchmark image:
  `ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@sha256:3ea1bc51ecbab7d5922cffb209f0e0323b9914ec1dedfb40cd82bace658abfc8`
- Fixture revision used by the workflow:
  `8d2c866ee315bdbed468b2e92e4587d85b6a5cc8`
- Latest Resolver fixture revision:
  `0556991b56c5f6e9753402ab2265232ce2577ae1`
- Result: blocked; metrics and result artifacts were not produced
- Cleanup: RunPod pod was removed successfully

The provider diagnostic was:

```text
PROVIDER_CONTENT_PROBE_FAILED
Can't instantiate abstract class ASRModel without an implementation for
abstract methods 'setup_training_data', 'setup_validation_data'
```

The failure occurred after pod startup, so it incurred provider execution
time. It was not a GHCR digest or RunPod image-pull failure.

## Root cause

The Resolver workflow had successfully produced a new fixture revision, but
the repository pointers in `rtf-scores/benchmark/` still referred to the
previous revision and previous Resolver image receipt. The benchmark workflow
accepted the stale pointer and proceeded to create a provider job without
checking that the fixture receipt was bound to the image selected for the
benchmark.

The local guarded RunPod smoke using the latest Resolver fixture completed
with content available and metrics, so the provider path itself was not
classified as generally unavailable.

## Remediation

The benchmark workflow now fails closed before RunPod pod creation when any of
the following identities differ:

1. fixture pointer revision and fixture receipt revision;
2. fixture repository in the receipt and the selected fixture repository;
3. receipt revision and selected fixture revision;
4. fixture receipt image digest and the selected GHCR image digest.

The contract workflow checks that these gates remain present. The benchmark
pointers are updated to the latest Resolver receipt and immutable GHCR digest.

This prevents stale fixture/image combinations from consuming HF Jobs or
RunPod resources. It does not claim that provider execution is successful;
the next safe unit is a new Actions smoke after this change is merged.

## Evidence and limitations

- GHCR publish and post-publish RTF Resolver completed successfully.
- Local RunPod guarded smoke completed with metrics and matching receipt SHA.
- Actions RunPod cleanup completed successfully.
- The failed Actions execution produced no accepted metrics.
- No private asset, model, or provider state was inferred from the error.

