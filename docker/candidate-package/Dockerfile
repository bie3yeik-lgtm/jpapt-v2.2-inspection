# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ARG SOURCE_REPOSITORY=unknown/unknown
ARG SOURCE_BUCKET=unknown/unknown
ARG CANDIDATE_ID=latest
ARG PACKAGE_NAME=jpapt-candidate

LABEL org.opencontainers.image.source="https://github.com/${SOURCE_REPOSITORY}" \
      io.jpapt.source.repository="${SOURCE_REPOSITORY}" \
      io.jpapt.source.bucket="${SOURCE_BUCKET}" \
      io.jpapt.candidate.id="${CANDIDATE_ID}" \
      io.jpapt.package.name="${PACKAGE_NAME}"

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/cache/huggingface \
    JPAPT_CANDIDATE_DIR=/opt/jpapt/candidate

WORKDIR /opt/jpapt

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip && \
    python -m pip install "huggingface_hub>=1.0,<2" onnx onnxruntime numpy

COPY .ci/candidate/ /opt/jpapt/candidate/
COPY scripts/ci/generic-candidate-evaluate.py /opt/jpapt/evaluate_candidate.py

# Generic contract: smoke/probe require only ONNX; parity consumes .npz files
# containing input__<tensor> and output__<tensor> arrays.
ENTRYPOINT ["python", "/opt/jpapt/evaluate_candidate.py"]
