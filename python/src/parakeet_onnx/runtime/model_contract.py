from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from .artifacts import CandidateArtifacts, CandidateMetadataError


InputKind = Literal["canonical_waveform", "features"]


class ModelContractError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelContract:
    input_kind: InputKind
    primary_input: str
    length_input: str | None
    logits_output: str
    blank_id: int
    decoder: str = "ctc"

    @classmethod
    def load(cls, candidate_dir: str | Path) -> "ModelContract":
        try:
            candidate = CandidateArtifacts.load(candidate_dir, verify_artifacts=False)
        except CandidateMetadataError as exc:
            raise ModelContractError(str(exc)) from exc
        return cls.from_candidate(candidate)

    @classmethod
    def from_candidate(cls, candidate: CandidateArtifacts) -> "ModelContract":
        if candidate.decoder != "ctc":
            raise ModelContractError(
                f"CTC ModelContract cannot load decoder {candidate.decoder!r}"
            )
        contract = candidate.runtime_contract
        input_kind = str(contract.get("input_kind", "canonical_waveform"))
        if input_kind not in {"canonical_waveform", "features"}:
            raise ModelContractError(f"unsupported input_kind: {input_kind!r}")

        io = contract.get("io")
        if not isinstance(io, Mapping):
            raise ModelContractError("runtime_contract.io must be an object")
        primary_io = io.get("primary")
        if not isinstance(primary_io, Mapping):
            raise ModelContractError("runtime_contract.io.primary must be an object")

        decoder_config = contract.get("decoder_config")
        if not isinstance(decoder_config, Mapping):
            raise ModelContractError("runtime_contract.decoder_config must be an object")

        try:
            primary_input = _string(primary_io, "input")
            logits_output = _string(primary_io, "logits_output")
            blank_id = int(decoder_config["blank_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelContractError("CTC runtime contract is incomplete") from exc

        length_value = primary_io.get("length_input")
        length_input = str(length_value) if length_value is not None else None
        return cls(
            input_kind=input_kind,  # type: ignore[arg-type]
            primary_input=primary_input,
            length_input=length_input,
            logits_output=logits_output,
            blank_id=blank_id,
            decoder="ctc",
        )


def _string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ModelContractError(f"{key} must be a non-empty string")
    return item
