# syntax=docker/dockerfile:1

FROM nvcr.io/nvidia/nemo-speech:26.07.00

LABEL org.opencontainers.image.source="https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection"
LABEL org.opencontainers.image.description="Canonical NeMo reference/export environment for jpapt Parakeet ONNX validation"
LABEL io.jpapt.source.repo_id="nvidia/parakeet-tdt_ctc-0.6b-ja"
LABEL io.jpapt.source.framework="nemo"
LABEL io.jpapt.ghcr.package="nemo-speech-26.07.00"
LABEL io.jpapt.role="reference-export"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/workspace/.cache/huggingface \
    TORCH_HOME=/workspace/.cache/torch

WORKDIR /workspace

# Utilities required by the ASR / ONNX development workflow.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        git \
        curl \
        jq \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Keep the NVIDIA-owned NeMo/PyTorch/CUDA stack intact. Add only project-side
# reference/evaluation tooling and pin the two runtime identities that are
# contractually pinned by this repository.
RUN python -m pip install --no-cache-dir \
        onnx \
        onnxruntime==1.28.0 \
        huggingface_hub==1.24.0 \
        "datasets>=3.0" \
        "jsonschema>=4.0" \
        "soundfile>=0.13" \
        "scipy>=1.14" \
        jiwer

CMD ["/bin/bash"]
