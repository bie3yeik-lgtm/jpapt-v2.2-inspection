# Self-hosted Docker RTF smoke

`.github/workflows/self-hosted-docker-smoke.yml` is a manual verification
workflow for a repository-owned self-hosted GitHub Actions runner.

The runner must expose a working Docker daemon to the runner process. The
workflow deliberately uses `runs-on: self-hosted` and invokes Docker on the
host; it does not use a GitHub-hosted runner or Docker-in-Docker.

The supported Docker platform output is `linux/amd64` or Docker Desktop's
equivalent `linux/x86_64`; other platforms fail closed because the validation
image is pinned to the amd64 Python manifest.

The workflow builds the small, digest-pinned
`docker/self-hosted-ci/Dockerfile`, mounts the checked-out repository read-only,
and runs the contract probe inside that image. The probe checks the RTF
workflow markers, the fixed Hugging Face error-import path, Python syntax, JSON
schemas, and shell syntax. It is not evidence of a GPU/provider benchmark.

Before dispatching, install Docker on the self-hosted runner and ensure the
runner account can execute `docker version` and `docker run` without an
interactive privilege escalation.
