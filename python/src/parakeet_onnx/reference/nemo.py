from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class NemoReferenceError(RuntimeError):
    pass


@dataclass(slots=True)
class NemoReference:
    model: Any
    repo_id: str
    revision: str

    @property
    def preprocessor(self) -> Any:
        value = getattr(self.model, "preprocessor", None)
        if value is None:
            raise NemoReferenceError(
                "Loaded NeMo model does not expose .preprocessor."
            )
        return value

    @property
    def tokenizer(self) -> Any:
        value = getattr(self.model, "tokenizer", None)
        if value is None:
            raise NemoReferenceError(
                "Loaded NeMo model does not expose .tokenizer."
            )
        return value


def load_pinned_nemo_model(
    *,
    repo_id: str,
    revision: str,
    map_location: str | None = None,
) -> NemoReference:
    if not revision or revision in {"main", "master", "HEAD", "latest"}:
        raise NemoReferenceError(
            "Canonical NeMo loading requires an explicit pinned revision."
        )

    try:
        import nemo.collections.asr as nemo_asr
    except ImportError as exc:
        raise NemoReferenceError(
            "NeMo is required for canonical reference loading. "
            "Run this path in the NeMo container."
        ) from exc

    model_cls = getattr(nemo_asr.models, "ASRModel", None)
    if model_cls is None:
        raise NemoReferenceError("NeMo ASRModel API is unavailable.")

    kwargs: dict[str, Any] = {"model_name": repo_id}
    if map_location is not None:
        kwargs["map_location"] = map_location

    # NeMo model APIs do not consistently expose a Hugging Face `revision`
    # parameter. Canonical callers must ensure the pinned artifact is resolved
    # before this loader is invoked. Keep the revision in provenance here.
    model = model_cls.from_pretrained(**kwargs)

    return NemoReference(
        model=model,
        repo_id=repo_id,
        revision=revision,
    )
