# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

# Keep this image small: it validates the self-hosted Docker execution path,
# not the heavyweight NeMo/RTF provider image.
FROM python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49

LABEL org.opencontainers.image.source="https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection"
LABEL io.jpapt.role="self-hosted-docker-contract"

COPY scripts/ci/run-self-hosted-docker-smoke.py /opt/jpapt/run-smoke.py
WORKDIR /workspace

ENTRYPOINT ["python", "/opt/jpapt/run-smoke.py"]
