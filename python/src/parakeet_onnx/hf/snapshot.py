from __future__ import annotations

from typing import Any

from .revisions import RevisionBundle


def normalized_revision_snapshot(bundle: RevisionBundle) -> dict[str, Any]:
    """Serialize a revision bundle without repeating runtime semantics.

    New normalized bundles use runtime.json as the only authored decoder/profile
    selector. reference.json and evaluation-schema.json therefore remain pure
    identity/rule documents. Legacy bundles without runtime.json retain their
    historical decoder snapshots for read compatibility.
    """

    value = bundle.to_dict()
    if bundle.runtime is None:
        return value

    runtime = value.get("runtime")
    if isinstance(runtime, dict):
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
