# jpapt-v2.2-inspection

## Protocol architecture

Candidate request/evaluation/completion work is split between an orchestrator Rust authority and a portable external receiver surface. Start with these documents before changing protocol workflows or helpers:

- [`docs/candidate-request-gateway.md`](docs/candidate-request-gateway.md) — preferred request entry point, execution identity, dry-run planning, and V2 dispatch flow.
- [`docs/candidate-protocol-runtime-boundary.md`](docs/candidate-protocol-runtime-boundary.md) — authoritative Rust vs portable Python responsibility boundary.
- [`docs/candidate-completion-protocol.md`](docs/candidate-completion-protocol.md) — receipt, rejection, ACK, lifecycle, persistence, retry, and trust semantics.
- [`docs/request-execution-identity.md`](docs/request-execution-identity.md) — logical request identity vs per-execution identity.
- [`docs/candidate-protocol-e2e.md`](docs/candidate-protocol-e2e.md) — manual dry-run cross-repository E2E and receiver bootstrap/readiness requirements.

Production orchestrator protocol construction and trust-boundary validation should use `rust/crates/asr-contracts`. Portable Python protocol helpers remain intentionally supported for receiver repositories that do not contain this Rust workspace. Do not remove the portable layer or migrate an external receiver to Rust without changing the receiver distribution contract.

Real external proofs remain distinct from local/static CI: cross-repository callback routing requires the dedicated fixture tracked by Issue #70, and real private Hugging Face lifecycle storage write/read proof is tracked by Issue #71.

## DirectML retirement

DirectML is retired from the active contract. New `directml` or
`windows-directml` requests are rejected and must not produce reviewed
execution receipts, HF Jobs runs, or Bucket completion evidence. Historical
workflows and artifacts remain available only for audit; see
[`docs/directml-retirement.md`](docs/directml-retirement.md).

## config/models

Parakeetについては **`default = "ctc"` を意図的に設定**しています。元モデルそのものはTDT-CTC hybridですが、今回のONNX/Rust開発ではまずCTCを成立させ、その後TDTへ広げるためです。これは上流モデルのdefault decoderを書き換えているのではなく、このRepositoryにおけるdeployment defaultという意味です。上流モデル自体はHybrid FastConformer TDT-CTCとして提供されています。
