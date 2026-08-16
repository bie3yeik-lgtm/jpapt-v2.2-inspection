from __future__ import annotations

from typing import Any

from .revisions import RevisionBundle, RevisionError


def normalized_revision_snapshot(bundle: RevisionBundle) -> dict[str, Any]:
    """Serialize the canonical four-document revision bundle.

    runtime.json is mandatory. Decoder/profile semantics remain centralized in
    the pinned ASR runtime catalog and are therefore not copied into reference
    or evaluation snapshots.
    """

    if bundle.runtime is None:
        raise RevisionError("runtime.json is required for the canonical config contract")

    value = bundle.to_dict()
    runtime = value["runtime"]
    if not isinstance(runtime, dict):
        raise RevisionError("runtime revision snapshot is missing")

    value["runtime"] = {
        "document_sha256": runtime["document_sha256"],
        "catalog": runtime["catalog"],
        "profile_set": runtime["profile_set"],
    }

    reference = value.get("reference")
    if isinstance(reference, dict):
        reference.pop("decoders", None)

    evaluation = value.get("evaluation_schema")
    if isinstance(evaluation, dict):
        evaluation.pop("decoders", None)

    return value
