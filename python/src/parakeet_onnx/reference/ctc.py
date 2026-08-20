from __future__ import annotations

from typing import Any

import numpy as np

from parakeet_onnx.audio.features import FeatureOutput


def ctc_reference_logits(
    model: Any,
    features: FeatureOutput,
) -> np.ndarray:
    """Run the model encoder/CTC head using already-produced features.

    The exact NeMo hybrid-model method surface is version-specific, so this
    adapter intentionally requires the loaded model to expose a callable
    `ctc_logits_from_features(features, lengths)` compatibility method.
    Export/reference integration should install that adapter in one place
    rather than guessing internal NeMo module names throughout the project.
    """
    method = getattr(model, "ctc_logits_from_features", None)
    if method is None:
        raise RuntimeError(
            "NeMo integration adapter is not installed: expected ctc_logits_from_features(features, lengths)."
        )
    value = method(features.features, features.length)
    return np.asarray(value, dtype=np.float32)
