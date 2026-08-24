# syntax=docker/dockerfile:1

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG FIXTURE_REVISION=unknown
ARG FIXTURE_MANIFEST_SHA256=unknown

LABEL io.jpapt.role="rtf-benchmark-smoke-fixture"
LABEL io.jpapt.fixture.revision="${FIXTURE_REVISION}"
LABEL io.jpapt.fixture.manifest_sha256="${FIXTURE_MANIFEST_SHA256}"

COPY . /opt/rtf-fixture
ENV RTF_BUNDLED_FIXTURE_DIR=/opt/rtf-fixture \
    RTF_BUNDLED_FIXTURE_REVISION=${FIXTURE_REVISION} \
    RTF_BUNDLED_FIXTURE_MANIFEST_SHA256=${FIXTURE_MANIFEST_SHA256}
