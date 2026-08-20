# #154 `jpapt-v2.2-inspection` public inspection bypass

## 目的

Private Actions の billing/spending limit が解消しない場合に、private package workflowを実行せず、public repository
[`bie3yeik-lgtm/jpapt-v2.2-inspection`](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection) の Candidate Request Gateway と HF Jobs Smoke 経路で、公開済みcandidateの実行・completion証跡を取得する。

この手順は #154 の実運用評価を迂回するためのものだが、private GitHub Actions artifactを偽装したり、local evidenceをtrusted private artifactへ昇格したりしない。

## 固定した外部正本と実行identity

| 項目 | 値 |
| --- | --- |
| public repository | `bie3yeik-lgtm/jpapt-v2.2-inspection` |
| inspected default-branch SHA | `149d689dfbc9a52774064305836c0ff45f5b7e9b` |
| source repository | `largoyo/Premiere-AutoProcess-Plugin` |
| HF Bucket | `gawohok7/premiere-autoprocess-plugin-bucket` |
| candidate | `candidate-000001` |
| candidate content digest | `sha256:e9861e822dcb24acd936142488c344dc6a4cbcb35b0b06e24a2a549d1419eb25` |
| public executable image | `ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec` |
| suite | `smoke` |
| executor | `hf_jobs` |
| environment | `linux-cpu` |

public正本のworkflow/docsで確認した不変条件は次のとおりである。

- `hf_bucket`、`candidate_id`、`hf_jobs_image` はdispatch payloadで明示できる。
- `hf_jobs_image` は匿名取得可能なimmutable `@sha256:` imageでなければならない。
- HF Jobsは `smoke` のみを受け付け、`parity`/`probe` は拒否する。
- `execute=false` はcandidate download/build/evaluation/HF Jobsを行わない計画・見積り段階である。
- `execute=true` はGatewayが新しい `request_execution_id` を生成し、V2 workflowをdispatchする。
- completion receipt、lifecycle、ACKはrequest identity・execution identity・image digestを保持する。

正本の参照先は、確認時点の [`docs/candidate-request-gateway.md`](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/blob/149d689dfbc9a52774064305836c0ff45f5b7e9b/docs/candidate-request-gateway.md)、[`docs/external-candidate-pipeline.md`](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/blob/149d689dfbc9a52774064305836c0ff45f5b7e9b/docs/external-candidate-pipeline.md)、[`docs/hf-buckets.md`](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/blob/149d689dfbc9a52774064305836c0ff45f5b7e9b/docs/hf-buckets.md) である。

## 前提条件

public repository側に次のEnvironment/Secretが設定済みであることを確認する。

- `HF_TOKEN`: `gawohok7/premiere-autoprocess-plugin-bucket` の read/write と HF Jobs smokeに必要な権限
- `SOURCE_REPO_TOKEN`: private source repositoryの必要なContents read権限
- `JPAPT_ACK_TOKEN`: private source repositoryへのcompletion ACK dispatch権限
- Environment名: `Private-Secrets`

dispatchを発行するcaller tokenは、public repositoryへ `repository_dispatch` を送れる権限だけを持つものとする。token値はshell trace、payload、artifact、作業履歴へ出力しない。

## 実行手順

### 1. plan-onlyを発行する

`dry_run=true` かつ `execute=false` で、public Gatewayへ `jpapt.candidate-request` を送る。`request_execution_id` は指定しない。Gatewayが所有する値をcallerが持ち込んではならない。

```bash
export PUBLIC_DISPATCH_TOKEN='使用環境から注入したtoken'

GH_TOKEN="$PUBLIC_DISPATCH_TOKEN" gh api \
  --method POST \
  repos/bie3yeik-lgtm/jpapt-v2.2-inspection/dispatches \
  -f event_type=jpapt.candidate-request \
  -F client_payload:='{
    "request_id": "jpapt-154-candidate-000001-plan",
    "source_repository": "largoyo/Premiere-AutoProcess-Plugin",
    "receipt_repository": "largoyo/Premiere-AutoProcess-Plugin",
    "hf_bucket": "gawohok7/premiere-autoprocess-plugin-bucket",
    "candidate_id": "candidate-000001",
    "package_name": "jpapt-candidate",
    "dataset_source": "bucket",
    "suite": "smoke",
    "executor": "hf_jobs",
    "environment": "linux-cpu",
    "hf_flavor": "cpu-basic",
    "hf_jobs_image": "ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec",
    "dry_run": true,
    "execute": false
  }'
```

HTTP 204はdispatch受付であり、評価成功ではない。public repositoryのGateway runで次を確認する。

- resolved Bucketが `gawohok7/premiere-autoprocess-plugin-bucket`
- resolved candidateが `candidate-000001`
- imageが上記のdigest-pinned reference
- suite/executor/environmentが `smoke`/`hf_jobs`/`linux-cpu`
- `execute=false` のためHF JobsやBucket mutationが発生していない

### 2. 同じlogical requestをexecuteする

planの内容をreviewした後、同じ `request_id` で `dry_run=false`、`execute=true` を発行する。これは新しいGateway executionであり、planと同じ `request_execution_id` を再利用しない。

```bash
GH_TOKEN="$PUBLIC_DISPATCH_TOKEN" gh api \
  --method POST \
  repos/bie3yeik-lgtm/jpapt-v2.2-inspection/dispatches \
  -f event_type=jpapt.candidate-request \
  -F client_payload:='{
    "request_id": "jpapt-154-candidate-000001-plan",
    "source_repository": "largoyo/Premiere-AutoProcess-Plugin",
    "receipt_repository": "largoyo/Premiere-AutoProcess-Plugin",
    "hf_bucket": "gawohok7/premiere-autoprocess-plugin-bucket",
    "candidate_id": "candidate-000001",
    "package_name": "jpapt-candidate",
    "dataset_source": "bucket",
    "suite": "smoke",
    "executor": "hf_jobs",
    "environment": "linux-cpu",
    "hf_flavor": "cpu-basic",
    "hf_jobs_image": "ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec",
    "dry_run": false,
    "execute": true
  }'
```

### 3. completion/ACKを確認する

public repositoryのGateway/V2 run、completion receipt、lifecycle artifact、HF Jobs resultを突合する。

最低限、次の同一性を確認する。

```text
source_repository == largoyo/Premiere-AutoProcess-Plugin
hf_bucket == gawohok7/premiere-autoprocess-plugin-bucket
candidate_id == candidate-000001
candidate_content_digest == sha256:e9861e822dcb24acd936142488c344dc6a4cbcb35b0b06e24a2a549d1419eb25
image == ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec
suite == smoke
executor == hf_jobs
environment == linux-cpu
```

成功条件は、Gatewayの `planned → dispatched → running`、V2/HF Jobsの完了、completion receipt、source repository側のACKが同じlogical requestとexecution identityを保持して `acknowledged` になることである。HTTP 204、workflow dispatch受理、HF Jobsの起動だけでは完了としない。

## #154受入れ上の扱い

この経路で取得できるのは、public inspection repositoryを実行主体とした external/provider evidence である。private Actionsの `hf-package-evidence-<run>-<attempt>` artifactを生成したことにはならない。

したがって、現行の `scripts/jpapt-verify-package-artifact.py` が要求する次のtrusted private builder条件は別扱いである。

- builder repositoryが `largoyo/Premiere-AutoProcess-Plugin`
- workflowが `.github/workflows/hf-model-bootstrap-package.yml`
- eventが `workflow_dispatch`
- branchが `main`
- artifact archive SHA、workflow run/attempt、head SHAがpackage evidenceと一致

private Actions billingを復旧できない間は、#154を「public inspection bypassによるexternal smoke evidence」として記録し、trusted private builder acceptanceやissue close条件へ自動昇格しない。close判断には、この区別を明記した人手reviewが必要である。

## 今回の実施範囲

- candidate作成、HF Bucket upload、base-image policy更新、GHCR push、Public化、exact digest匿名pullは完了済み。
- 本runbookのpublic Gateway plan/execute dispatch、HF Jobs、completion/ACKは、HF computeと外部callbackを発生させるため、この文書作成時点では未実行。
