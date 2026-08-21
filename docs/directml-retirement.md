# DirectML route retirement

As of 2026-08-20, DirectML is retired from the active JPAPT inspection
contract. New requests, repository dispatches, reviewed execution receipts,
HF Jobs/Bucket completion claims, and acceptance evidence MUST NOT use the
DirectML provider or the Windows DirectML route. The old schemas and
historical artifacts remain readable for audit and migration only; the former
workflow files and executable receipt builder have been removed. A resolver
or reviewer must reject a new
`directml`/`windows-directml` request rather than schedule it.

Active acceptance uses Linux CPU/CUDA or other explicitly supported routes.
This policy applies to the inspection repository and to parent repositories
that consume its contracts.
