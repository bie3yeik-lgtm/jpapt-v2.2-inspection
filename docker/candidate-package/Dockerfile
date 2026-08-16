# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ARG SOURCE_REPOSITORY=unknown/unknown
ARG SOURCE_BUCKET=unknown/unknown
ARG CANDIDATE_ID=latest
ARG PACKAGE_NAME=jpapt-candidate
ARG RUNTIME_ENVIRONMENT=linux-cpu
ARG ORT_PACKAGE=onnxruntime

LABEL org.opencontainers.image.source="https://github.com/${SOURCE_REPOSITORY}" \
      io.jpapt.source.repository="${SOURCE_REPOSITORY}" \
      io.jpapt.source.bucket="${SOURCE_BUCKET}" \
      io.jpapt.candidate.id="${CANDIDATE_ID}" \
      io.jpapt.package.name="${PACKAGE_NAME}" \
      io.jpapt.runtime.target_environment="${RUNTIME_ENVIRONMENT}" \
      io.jpapt.runtime.target_ort_package="${ORT_PACKAGE}" \
      io.jpapt.package.execution_platform="linux"

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/cache/huggingface \
    JPAPT_CANDIDATE_DIR=/opt/jpapt/candidate

WORKDIR /opt/jpapt

# The OCI package itself is Linux. For Linux CUDA it carries onnxruntime-gpu;
# for CPU/macOS/Windows targets it carries Linux onnxruntime. CoreML and
# DirectML evidence is produced natively by the corresponding hosted runner,
# not by pretending a Linux container can execute those providers.
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip && \
    if [ "${RUNTIME_ENVIRONMENT}" = "linux-cuda" ]; then IMAGE_ORT_PACKAGE=onnxruntime-gpu; else IMAGE_ORT_PACKAGE=onnxruntime; fi && \
    python -m pip install "huggingface_hub>=1.0,<2" onnx numpy "${IMAGE_ORT_PACKAGE}"

COPY .ci/candidate/ /opt/jpapt/candidate/
COPY scripts/ci/generic-candidate-evaluate.py /opt/jpapt/evaluate_candidate.py

# Generic contract: smoke/probe require only ONNX; parity consumes .npz files
# containing input__<tensor> and output__<tensor> arrays. Provider fallback is
# intentionally disabled by default in evaluate_candidate.py.
ENTRYPOINT ["python", "/opt/jpapt/evaluate_candidate.py"]
