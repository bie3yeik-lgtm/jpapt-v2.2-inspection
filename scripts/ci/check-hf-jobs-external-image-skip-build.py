#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

WORKFLOW = Path('.github/workflows/candidate-package-evaluate-v2.yml')
text = WORKFLOW.read_text(encoding='utf-8')
build = text[text.index('\n  build:'):text.index('\n  github-linux-cpu:')]
hf_jobs = text[text.index('\n  hf-jobs:'):text.index('\n  completion:')]
completion = text[text.index('\n  completion:'):]

skip = "needs.resolve.outputs.executor != 'hf_jobs' || needs.resolve.outputs.hf_jobs_image == ''"
external = '[[ "$EXECUTOR" == hf_jobs && -n "$HF_JOBS_IMAGE" ]]'

# Candidate identity is always resolved, but external HF Jobs images do not
# materialize model bytes merely to construct an unused package.
assert 'Resolve candidate identity and materialize only when building' in build
assert 'bash scripts/hf/hf-fetch-candidate.sh "${CANDIDATE_ID:-}" --resolve-only' in build
assert 'bash scripts/hf/hf-fetch-candidate.sh "${CANDIDATE_ID:-}"' in build
assert external in build

# BuildKit setup, GHCR authentication, and the push itself all share the same
# no-override condition. An external immutable HF Jobs image therefore cannot
# accidentally trigger a second package publication.
assert build.count(skip) == 3, build.count(skip)
assert 'uses: docker/setup-buildx-action@v3' in build
assert 'uses: docker/login-action@v3' in build
assert 'name: Build and push immutable package' in build
assert '--push' in build

# Downstream jobs consume one normalized package authority. External images must
# be immutable lowercase sha256 references; GitHub/no-override paths consume the
# Buildx digest outputs instead.
assert 'image_ref: ${{ steps.package.outputs.image_ref }}' in build
assert 'image_digest: ${{ steps.package.outputs.image_digest }}' in build
assert 'name: Select package image authority' in build
assert 'id: package' in build
assert 'hf_jobs_image override must be an immutable lowercase sha256 digest reference' in build
assert 'image_digest="${HF_JOBS_IMAGE##*@}"' in build
assert 'image_ref="$BUILT_IMAGE_REF"' in build
assert 'image_digest="$BUILT_IMAGE_DIGEST"' in build

# HF Jobs still plans from the selected build-job output and independently sees
# the explicit override; anonymous-pull preflight remains after Rust selection.
assert 'BUILT_IMAGE: ${{ needs.build.outputs.image_ref }}' in hf_jobs
assert 'HF_JOBS_IMAGE_OVERRIDE: ${{ needs.resolve.outputs.hf_jobs_image }}' in hf_jobs
assert 'IMAGE_REF: ${{ steps.plan.outputs.image }}' in hf_jobs
assert 'hf-jobs-image-preflight.sh "$IMAGE_REF"' in hf_jobs

# Receipt construction receives the normalized selected image plus the HF Jobs
# plan-selected image. Existing Rust receipt contracts require the HF Jobs image
# binding to win for executor=hf_jobs.
assert 'IMAGE_REF: ${{ needs.build.outputs.image_ref }}' in completion
assert 'IMAGE_DIGEST: ${{ needs.build.outputs.image_digest }}' in completion
assert 'HF_JOBS_IMAGE_REF: ${{ needs.hf-jobs.outputs.image_ref }}' in completion
assert 'HF_JOBS_IMAGE_DIGEST: ${{ needs.hf-jobs.outputs.image_digest }}' in completion

print('HF Jobs external-image build-skip contract passed')
