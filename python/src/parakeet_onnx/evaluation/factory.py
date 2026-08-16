from __future__ import annotations

from dataclasses import dataclass

from parakeet_onnx.runtime.artifacts import CandidateArtifacts
from parakeet_onnx.runtime.factory import create_runtime_adapter

from .pipeline import PythonAsrEvaluator


@dataclass(frozen=True, slots=True)
class EvaluatorBuildRequest:
    run_id: str
    provider_id: str
    candidate: CandidateArtifacts


def create_python_evaluator(request: EvaluatorBuildRequest) -> PythonAsrEvaluator:
    adapter = create_runtime_adapter(
        candidate=request.candidate,
        provider_id=request.provider_id,
    )
    return PythonAsrEvaluator(
        run_id=request.run_id,
        adapter=adapter,
        provider_id=request.provider_id,
    )
