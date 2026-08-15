from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal


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
        root = Path(candidate_dir).expanduser().resolve()
        path = root / "metadata.json"
        if not path.is_file():
            raise ModelContractError(
                f"candidate metadata is missing: {path}"
            )

        raw = json.loads(path.read_text(encoding="utf-8"))
        contract = raw.get("runtime_contract")
        if not isinstance(contract, dict):
            raise ModelContractError(
                "metadata.json must contain a runtime_contract object."
            )

        try:
            input_kind = str(contract["input_kind"])
            primary_input = str(contract["primary_input"])
            logits_output = str(contract["logits_output"])
            blank_id = int(contract["blank_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelContractError(
                "runtime_contract is incomplete."
            ) from exc

        if input_kind not in {"canonical_waveform", "features"}:
            raise ModelContractError(
                f"unsupported input_kind: {input_kind!r}"
            )

        length_value = contract.get("length_input")
        length_input = (
            str(length_value) if length_value is not None else None
        )

        return cls(
            input_kind=input_kind,  # type: ignore[arg-type]
            primary_input=primary_input,
            length_input=length_input,
            logits_output=logits_output,
            blank_id=blank_id,
            decoder=str(contract.get("decoder", "ctc")),
        )
