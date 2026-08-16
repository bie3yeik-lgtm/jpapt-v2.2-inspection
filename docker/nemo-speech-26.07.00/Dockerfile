# syntax=docker/dockerfile:1

FROM nvcr.io/nvidia/nemo-speech:26.07.00

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

# ONNX development/evaluation tools.
#
# Keep NeMo/PyTorch/CUDA from the official NVIDIA image intact.
# Add only the tools that are not part of the canonical base environment.
RUN python -m pip install --no-cache-dir \
        onnx \
        onnxruntime \
        huggingface_hub \
        jiwer

CMD ["/bin/bash"]
