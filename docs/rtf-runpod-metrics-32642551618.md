# RunPod RTF metrics receipt: 2026-08-24

## Execution

- GitHub Actions run: [32642551618](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32642551618)
- provider: RunPod Pod
- GPU: RTX 3090
- inspection profile: `smoke`
- batch size: `1`
- model revision: `44edb27eea9317daf89333e75eb830db4b1cc298`
- dataset revision: `bf8819e8d9a5feb51b0c718686bd20ea67a3c729`
- image: `ghcr.io/bie3yeik-lgtm/parakeet-rtf-benchmark@sha256:f0b9dbbf4a9ebd83af1eafa7c311d5e2facc0fa2b2d03b8554b751667647f487`
- fixture revision: `cdcd04b474a64bb40f8de8a2f01296ed7dbf1954`
- result persistence PR: [#462](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/pull/462) (merged)

## Metrics

The immutable result is stored at:

<https://huggingface.co/datasets/gawohok7/rtf-benchmark-fixtures/resolve/34d484c4af45a6775d844131c82d1a106c222e92/results/rtf-runpod-32642551618-b1/metrics.json>

| Field | Value |
|---|---:|
| audio duration | 5402.784 sec |
| processing duration | 15.490207185968757 sec |
| RTF | 0.0028670787479138085 |
| RTFx | 348.78707141463644 |
| CER | 0.5555158304532635 |
| GPU price | 0.5 USD/hour |
| GPU utilization | 88.22988505747128% |
| peak VRAM | 5606215680 bytes (5346.50390625 MB) |
| metrics SHA-256 | `50a3e7a046c1bc3a40f3c26ba9b6cc1a73d0b8ec5412da3e98f158a1d1be96dc` |

The Rust service-result validation and benchmark-record generation succeeded.
The RunPod Pod was cleaned up by the workflow after result collection.

## Ranking status

The smoke ranking workflow was run after merging PR #462, but Rust ranking
stopped on an older completed record whose `cer` and `gpu_price_per_hour` are
null. The new RunPod record is complete; the ranking input set is not yet
uniformly valid because the historical record remains in
`rtf-scores/smoke/hf-jobs/t4/batch-1/benchmark-record.json`.

Required follow-up:

1. Re-run or replace the historical incomplete smoke record with complete
   metrics, or explicitly classify it as excluded historical data.
2. Re-run `Generate RTF Benchmark Ranking` with `phase=smoke`.
3. Confirm the generated ranking PR contains the RunPod RTX 3090 result.

This document records the successful RunPod evidence and does not alter the
historical record or claim that the ranking is complete.
