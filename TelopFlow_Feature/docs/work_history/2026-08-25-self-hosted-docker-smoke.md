# self-hosted Docker RTF smoke

## 目的

RTF fixture image build failure後の同種不備を監査し、repository-owned
self-hosted runnerでDockerを使う再現可能なGitHub Actions検証経路を追加する。

## 変更

- `.github/workflows/self-hosted-docker-smoke.yml`
- `docker/self-hosted-ci/Dockerfile`
- `scripts/ci/run-self-hosted-docker-smoke.py`
- `docs/self-hosted-docker-smoke.md`

## 実装・検証

検証イメージはPython 3.12 slimのlinux/amd64 manifest digestを固定し、
repositoryをread-only mountしてRTF workflow marker、Hugging Face error import、
Python/JSON/shell契約を検査する。self-hosted workflowは`runs-on: self-hosted`で
Docker daemonの利用可否、build、run、cleanupを実行する。

このホストではworkflow変更後に次を実行する。

```text
docker version
docker build --pull=false -f docker/self-hosted-ci/Dockerfile ...
docker run ... jpapt-self-hosted-docker-smoke
```

GitHub Actions上のself-hosted runner実行は、このローカル作業だけでは未検証であり、
workflow_dispatchによる外部実行が必要である。GPU推論、RunPod、HF Jobsの成功証拠も
このsmoke workflowの受入範囲外である。

## 実行結果

- `docker build --pull=false -f docker/self-hosted-ci/Dockerfile ...`: PASS
- Docker read-only mountによる `self-hosted Docker RTF smoke`: PASS
- 全 workflow YAML parse: PASS
- `bash scripts/ci/test-runpod-cuda-probe.sh`: PASS
- `RUSTC_WRAPPER= cargo run --locked -p asr-contracts --bin asr-workflow-dispatch -- validate`: PASS（101 workflow）
- `git diff --check`: PASS
- Docker platform check: PASS (`linux/x86_64`, accepted as amd64 equivalent)
- Expanded Docker probe: all `scripts/**/*.sh`, RTF entrypoint, and evaluation schema JSON files: PASS
- 通常の `mise run actions-validate` はsccache serverの通信エラーで失敗。ソース変更のエラーではなく、wrapperを無効化した再実行でPASS。

併せて、既存contract workflowが非実行権限のshell testを直接呼んでいたため、
`bash`経由の呼び出しへ修正した。

## GitHub Actions受入れ

- `32778400521`: self-hosted Docker jobは成功。既存contract jobは古いRunPod cloud-type契約で失敗。
- `32778630579`: self-hosted Docker jobは成功。既存contract jobはPhase 1 matrixの旧件数12で失敗。
- `32778786912`: self-hosted Docker jobと既存RTF contract jobの両方が成功。

最終受入れrunのself-hosted jobは `97595911275`、既存contract jobは
`97595911098` であり、いずれもcommit `69b3cca`をcheckoutして実行された。
RunPod実GPU推論の成功を意味するものではなく、今回の受入れ範囲はDocker・workflow・
契約検査である。
