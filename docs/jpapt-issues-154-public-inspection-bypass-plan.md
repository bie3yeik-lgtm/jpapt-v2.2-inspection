# Issue #154 Public Inspection Bypass 実装計画

作成日: 2026-08-20
対象ブランチ: `feat/issue-154-public-inspection-bypass-prep`
親Issue: `largoyo/Premiere-AutoProcess-Plugin#154`
参照runbook: [`jpapt-issues-154-public-inspection-bypass.md`](jpapt-issues-154-public-inspection-bypass.md)

## 目的

private GitHub Actionsのbilling/spending limitが解消しない場合に、public repository
`bie3yeik-lgtm/jpapt-v2.2-inspection`のCandidate Request GatewayとHF Jobs Smoke経路で、
公開済みcandidateの実行結果・completion・ACKを取得するための実装準備を行う。

この経路で得られる証拠はpublic inspection repositoryのexternal/provider evidenceであり、
private Actionsのtrusted package artifactを代替しない。#154をcloseする際は、この境界を
明記した人手reviewを必須とする。

## 固定する正本・identity

参照runbookに記録された次の値を、実行時に再解決して差し替えない。

| 項目 | 固定値 |
|---|---|
| public repository | `bie3yeik-lgtm/jpapt-v2.2-inspection` |
| inspected default-branch SHA | `149d689dfbc9a52774064305836c0ff45f5b7e9b` |
| source repository | `largoyo/Premiere-AutoProcess-Plugin` |
| HF Bucket | `gawohok7/tf-v2.2-onnx-dev-bucket` |
| candidate | `candidate-000001` |
| candidate digest | `sha256:e9861e822dcb24acd936142488c344dc6a4cbcb35b0b06e24a2a549d1419eb25` |
| executable image | `ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec` |
| suite / executor / environment | `smoke` / `hf_jobs` / `linux-cpu` |

## 作業単位

各unitはOrient → Define → Prove → Implement → Verify → Acceptの順で完了させる。

### Unit 0: 正本と権限の確認

- public repositoryの対象SHA、workflow、docs、schemaを取得し、runbookの固定値と照合する。
- `Private-Secrets` Environmentの`HF_TOKEN`、`SOURCE_REPO_TOKEN`、`JPAPT_ACK_TOKEN`の
  存在と用途を確認する。値は表示・保存しない。
- caller tokenがpublic repositoryへ`repository_dispatch`を発行できることを確認する。
- 実行主体、source repository、receipt repository、callback先を明記する。

受入れ条件: 固定値の照合表と権限表があり、token値がログ・artifact・commitに含まれない。

### Unit 1: plan-only dispatch

- `event_type=jpapt.candidate-request`をpublic Gatewayへ送る。
- `dry_run=true`、`execute=false`、`request_execution_id`未指定とする。
- payloadはrunbookの`request_id`、Bucket、candidate、image digest、suite、executor、
  environmentから生成する。
- HTTP 204は受付証拠に限定し、Gateway runでresolved identityと副作用なしを確認する。

受入れ条件: planが`candidate-000001`、指定Bucket、`ctc` runtime variant、実build済みdigest image、`smoke/hf_jobs/linux-cpu`
へ解決され、HF Jobs起動・Bucket mutationが発生していない。

### Unit 2: execute dispatch

- Unit 1の内容を人手reviewした後、同じlogical `request_id`で再度dispatchする。
- `dry_run=false`、`execute=true`とし、`request_execution_id`はGatewayに生成させる。
- planのexecution identityを再利用しない。
- Gatewayの`planned → dispatched → running`遷移を保存する。

受入れ条件: V2 workflowとHF Jobsが、固定candidate/image/suite/environmentで実行される。

### Unit 3: completion・lifecycle・ACKの突合

- completion receipt、lifecycle artifact、HF Jobs resultを取得する。
- source repositoryへのACKを、同じlogical requestとexecution identityで照合する。
- 次のidentityを全証跡で一致させる。

```text
source_repository
receipt_repository
hf_bucket
candidate_id
candidate_content_digest
image digest
suite / executor / environment
request_id / request_execution_id
```

受入れ条件: Gateway受付だけでなく、HF Jobs完了、completion receipt、ACKが一致している。

### Unit 4: #154 close判断資料

- public external/provider evidenceとprivate trusted package evidenceを別表にする。
- `scripts/jpapt-verify-package-artifact.py`が要求するprivate builder条件を確認する。
- private Actions artifactをpublic証跡から生成・偽装・昇格しない。
- #154 close提案には、public bypassで解消できた範囲、private acceptanceの未達範囲、
  残存リスク、reviewer判断を記載する。

受入れ条件: close判断が「external smoke evidence」と「trusted private builder acceptance」
を混同していない。

## 実装対象

現行public repositoryに不足がある場合、次を実装する。

- 固定payloadを生成するnon-secret dispatch wrapper
- plan/executeを分けたrequest identity検証
- Gateway/V2/HF Jobs receiptのschema・digest・identity検証
- completion/ACK収集とmachine-readable突合結果
- token redactionを含むGitHub Actions summary・artifact保存
- #154 close判断用のexternal/private evidence report

既存のpublic workflowがこれらを満たす場合は、重複実装せず、固定SHAでのcontract testと
実行証跡収集を追加する。

## 実行コマンドと証跡

実行前に必ずplan-onlyを行い、受付と評価成功を混同しない。

```bash
GH_TOKEN="$PUBLIC_DISPATCH_TOKEN" gh api \
  --method POST \
  repos/bie3yeik-lgtm/jpapt-v2.2-inspection/dispatches \
  -f event_type=jpapt.candidate-request \
  -F client_payload:='{"request_id":"jpapt-154-candidate-000001-plan","candidate_id":"candidate-000001","suite":"smoke","executor":"hf_jobs","environment":"linux-cpu","dry_run":true,"execute":false}'
```

HTTP 204はdispatch受付のみであり、PASS条件ではない。run URL、workflow run、job result、
completion receipt、lifecycle artifact、ACKをrun IDとexecution identityで保存する。

## 検証マトリクス

| 検証対象 | 必須証拠 | 不足時の扱い |
|---|---|---|
| public Gateway | resolved request/candidate/image | `NOT VERIFIED` |
| HF Jobs Smoke | job ID、provider実行、completion result | `BLOCKED` |
| completion receipt | digest・identity一致 | `NOT VERIFIED` |
| source ACK | request/execution identity一致 | `NOT VERIFIED` |
| private package evidence | trusted private builder条件 | public証拠へ昇格しない |
| #154 close | reviewerによる境界確認 | close提案を保留 |

## 非目標・安全境界

- private Actions artifactの偽装、再署名、trusted扱いへの昇格をしない。
- tokenをpayload、ログ、artifact、work historyへ出力しない。
- `execute=false`のplan-onlyでcandidate download/build/evaluation/HF Jobsを発生させない。
- 固定SHA・digest・request identityを省略した実行を成功扱いしない。
- provider未実行、HF compute不足、callback不足を推測で補完しない。

## 現時点の状態と次の安全な作業

このcommitでは、参照runbookを追跡対象にし、上記の実装・検証・受入れ作業を依存順に
定義する。plan/execute dispatch、HF Jobs、completion/ACKは外部computeとcallbackを
発生させるため、権限と実行承認を確認してから着手する。最初の実装単位は、固定SHAの
public workflow contractを読み取り、Unit 0の照合表を作ることである。

## 実装着手記録 (2026-08-20)

`recursive-delivery-entry-jpapt-issues-154-20260820.md`を着手エントリーとして追加した。
既存public workflowを確認した結果、Gatewayのplan/execute分離、Gateway-owned execution
identity、HF Jobs routing、completion/ACK/lifecycle契約は既に実装されているため、同じ責務を
重複実装しない。Unit 0はstatic contract確認を受入れ、Unit 1〜3のremote実行とUnit 4の
close判断は未実行・openとして記録した。

検証境界:

```text
workflow/source/schema inspection: PASS
local plan-only payload normalization: PASS
local worktree external side effect: NONE
public repository_dispatch: NOT RUN
HF Jobs: NOT RUN
completion/lifecycle/ACK: NOT VERIFIED
private trusted builder acceptance: NOT VERIFIED
```

Unit 1 local dispatch wrapper (2026-08-20):
`scripts/ci/dispatch-public-inspection-bypass.sh`を追加した。`plan`は`dry_run=true`/
`execute=false`、`execute`は`dry_run=false`/`execute=true`を生成し、callerが
`request_execution_id`を指定できない。`--print`で外部dispatchなしのpayload検証ができ、通常時は
既存の`repository-dispatch-with-retry.sh`を介してpublic Gatewayへ送る。

実行記録 (2026-08-20): plan-only Gateway run `32328515323`は、transport制限で包まれた
`protocol_payload`を正規化側が展開せず`source_repository must be string`で拒否された。
HF Jobs、V2 dispatch、candidate取得、completion/ACKは未発生。正規化側修正とnested payloadの
local contract testはPASS、remote修正確認は未実施であり、Unit 1はBLOCKEDとする。

再検証記録 (2026-08-20): payload正規化修正をmainへ反映後、Gateway run
`32328830992`を実行した。正規化処理は通過したが、source repository
`largoyo/Premiere-AutoProcess-Plugin`はprivateであり、Gatewayの`SOURCE_REPO_TOKEN`が空のため
`.jpapt/hf-bucket.yml`取得とrepository probeが404で失敗した。HF Jobs、V2 dispatch、candidate
取得、completion/ACKは未発生。この工程の継続には、source repository Contents read権限を持つ
`SOURCE_REPO_TOKEN`をGateway repositoryへ登録する必要がある。

Unit 0 read-only remote verification (2026-08-20): public `main`は固定SHA
`149d689dfbc9a52774064305836c0ff45f5b7e9b`と一致した。固定SHA上のGateway workflow、V2
workflow、completion receipt schemaを取得し、`jpapt.candidate-request`、`dry_run`、
`execute`、orchestrator-owned `request_execution_id`、digest-pinned image、completion/ACK/
lifecycle identityの契約を確認した。remote write、HF Jobs、source ACKは実行していない。
