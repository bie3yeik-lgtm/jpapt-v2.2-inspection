# syntax=docker/dockerfile:1

ARG NEMO_IMAGE=nvcr.io/nvidia/nemo-speech:26.07.00
FROM ${NEMO_IMAGE}

ARG NEMO_IMAGE
ARG SOURCE_REVISION=unknown
ARG RUNNER_VERSION=rtf-benchmark-v1

LABEL org.opencontainers.image.source="https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection"
LABEL org.opencontainers.image.revision="${SOURCE_REVISION}"
LABEL org.opencontainers.image.base.name="${NEMO_IMAGE}"
LABEL io.jpapt.ghcr.package="parakeet-rtf-benchmark"
LABEL io.jpapt.source.repo_id="nvidia/parakeet-tdt_ctc-0.6b-ja"
LABEL io.jpapt.role="rtf-benchmark"
LABEL io.jpapt.dataset.id="japanese-asr/ja_asr.common_voice_8_0"
LABEL io.jpapt.runner.version="${RUNNER_VERSION}"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HOME=/workspace/.cache/huggingface TORCH_HOME=/workspace/.cache/torch
# Optional model-level profiling (separate from timed RTF). Artifacts land under
# /output/profiler when RTF_PYTORCH_PROFILER=1 is set at runtime.
ENV RTF_PYTORCH_PROFILER_OUTPUT_DIR=/output/profiler
WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 ca-certificates curl jq openssh-server \
    && rm -rf /var/lib/apt/lists/*

COPY docker/rtf-benchmark/requirements.lock /tmp/rtf-requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/rtf-requirements.lock
COPY docker/rtf-benchmark/benchmark-runner /opt/rtf-benchmark/benchmark-runner
COPY docker/rtf-benchmark/entrypoint.sh /opt/rtf-benchmark/entrypoint.sh
RUN chmod +x /opt/rtf-benchmark/entrypoint.sh \
    && find /opt/rtf-benchmark/benchmark-runner -type f -name '*.py' -print0 \
      | xargs -0 -r python -m py_compile \
    && PYTHONPATH=/opt/rtf-benchmark/benchmark-runner \
      python -c 'import benchmark_runner; import benchmark_runner.load_fixture; import benchmark_runner.pytorch_profiler' \
    && PYTHONPATH=/opt/rtf-benchmark/benchmark-runner \
      python -m benchmark_runner.pytorch_profiler --smoke-test

ENV PYTHONPATH=/opt/rtf-benchmark/benchmark-runner
ENTRYPOINT ["/opt/rtf-benchmark/entrypoint.sh"]
CMD ["sleep", "infinity"]
