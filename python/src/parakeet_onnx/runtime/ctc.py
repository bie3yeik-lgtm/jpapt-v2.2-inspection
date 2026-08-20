from __future__ import annotations

from time import perf_counter

from parakeet_onnx.audio.features import FeatureExtractor
from parakeet_onnx.audio.resample import CanonicalAudio
from parakeet_onnx.decoding.ctc import greedy_ctc_ids

from .adapter import RuntimeTranscription
from .inference import OrtCtcRunner


class CtcRuntimeAdapter:
    decoder_id = "ctc"

    def __init__(
        self,
        *,
        runner: OrtCtcRunner,
        tokenizer: object,
        feature_extractor: FeatureExtractor | None = None,
    ) -> None:
        self.runner = runner
        self.tokenizer = tokenizer
        self.feature_extractor = feature_extractor

    def transcribe(self, audio: CanonicalAudio) -> RuntimeTranscription:
        frontend_ms: float | None = None
        if self.runner.contract.input_kind == "canonical_waveform":
            inference = self.runner.run_waveform(audio)
        else:
            if self.feature_extractor is None:
                raise RuntimeError("candidate expects external frontend features, but no FeatureExtractor was supplied")
            started = perf_counter()
            features = self.feature_extractor.extract(audio)
            frontend_ms = (perf_counter() - started) * 1000.0
            inference = self.runner.run_features(features)

        started = perf_counter()
        logits = inference.logits
        token_ids = greedy_ctc_ids(
            logits[0] if logits.ndim == 3 else logits,
            blank_id=self.runner.contract.blank_id,
        )
        if not isinstance(token_ids, list) or (token_ids and isinstance(token_ids[0], list)):
            raise RuntimeError("unexpected batched token result")
        ids = [int(item) for item in token_ids]
        text = _ids_to_text(self.tokenizer, ids)
        decoder_ms = (perf_counter() - started) * 1000.0
        return RuntimeTranscription(
            text=text,
            token_ids=ids,
            inference_ms=inference.inference_ms,
            decoder_ms=decoder_ms,
            frontend_ms=frontend_ms,
        )


def _ids_to_text(tokenizer: object, token_ids: list[int]) -> str:
    if hasattr(tokenizer, "ids_to_text"):
        return str(tokenizer.ids_to_text(token_ids))  # type: ignore[attr-defined]
    if hasattr(tokenizer, "decode"):
        return str(tokenizer.decode(token_ids))  # type: ignore[attr-defined]
    if hasattr(tokenizer, "tokenizer") and hasattr(tokenizer.tokenizer, "decode"):  # type: ignore[attr-defined]
        return str(tokenizer.tokenizer.decode(token_ids))  # type: ignore[attr-defined]
    raise TypeError("Unsupported tokenizer object: no ids_to_text/decode method")
