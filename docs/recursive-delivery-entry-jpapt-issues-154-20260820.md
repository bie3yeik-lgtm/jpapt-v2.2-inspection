# Recursive Delivery Entry: Issue #154 Public Inspection Bypass

作成日: 2026-08-20
対象ブランチ: `feat/issue-154-public-inspection-bypass-prep`
適用スキル: `.agents/skills/recursive-delivery-abstruct/SKILL.md`
親Issue: `largoyo/Premiere-AutoProcess-Plugin#154`
正本: [`jpapt-issues-154-public-inspection-bypass.md`](jpapt-issues-154-public-inspection-bypass.md)
計画: [`jpapt-issues-154-public-inspection-bypass-plan.md`](jpapt-issues-154-public-inspection-bypass-plan.md)

## 着手目的

private GitHub Actionsのbilling/spending limitが継続する場合に、public inspection
repositoryのCandidate Request GatewayとHF Jobs Smoke経路から、公開candidateの実行・
completion・ACK証跡を取得し、Issue #154のclose判断に利用できる状態を作る。

public external/provider evidenceはprivate Actionsのtrusted package evidenceを代替しない。
この境界を壊さず、固定identity、request execution identity、image digest、candidate digest、
completion、lifecycle、ACKを機械的に突合できる状態を受入れとする。

## 固定identity

| 項目 | 固定値 |
|---|---|
| public repository | `bie3yeik-lgtm/jpapt-v2.2-inspection` |
| inspected default-branch SHA | `149d689dfbc9a52774064305836c0ff45f5b7e9b` |
| source / receipt repository | `largoyo/Premiere-AutoProcess-Plugin` |
| HF Bucket | `gawohok7/tf-v2.2-onnx-dev-bucket` |
| candidate / candidate digest | `candidate-000001` / `sha256:e9861e822dcb24acd936142488c344dc6a4cbcb35b0b06e24a2a549d1419eb25` |
| executable image | `ghcr.io/bie3yeik-lgtm/jpapt-candidate@sha256:ee2ae53d748b0c3a748d306621d218787c1ff4aa76c6fedf8045a4c3c0803bec` |
| suite / executor / environment | `smoke` / `hf_jobs` / `linux-cpu` |

## Recursive unit state

### Unit 0: 正本・権限・identity

Orient/Define/Proveを完了した。現行public repositoryのworkflow/docs/schemaをローカルで
確認し、次の実装境界を確定した。

- Gatewayは`repository_dispatch` type `jpapt.candidate-request`を受け付ける。
- `execute=false`はresolve/estimate-onlyで、V2/HF Jobsを起動しない。
- `execute=true`だけがV2 workflow dispatchへ進む。
- Gatewayが`request_execution_id`を生成し、caller指定値をauthorityとして扱わない。
- V2、completion receipt、lifecycle、ACKへexecution identityを伝播する。
- HF Jobs imageはdigest-pinnedで、匿名取得可能であることが前提となる。
- `SOURCE_REPO_TOKEN`は外部receipt/callback、`HF_TOKEN`はHF経路、`JPAPT_ACK_TOKEN`はACK受領側の権限である。

受入れ状態: `STATIC PASS`。remote default branchが固定SHA
`149d689dfbc9a52774064305836c0ff45f5b7e9b`であることをread-only APIで確認した。
対象blobはGateway `45f8c7c5aef1654ce30e84b541f5ac9051eea0e5`、V2
`b938fe0480d501a122c9e4835aa6f1d89f2e0a5f`、receipt schema
`033db0e3ef334be72e2e28197e367a0d4ab1786a`である。secret権限、固定SHA上のremote run state、
外部callback権限は未検証。

### Unit 1: plan-only dispatch

実装入口は既存のGatewayとする。固定payload生成と`dry_run=true`、`execute=false`、
execution identity未指定をcontract testで検証する。HTTP 204は受付証拠に限定する。

受入れ状態: `LOCAL CONTRACT PASS / REMOTE NOT RUN`。固定payloadのlocal normalizationで
`request_id`、Gateway-owned `request_execution_id`、`dry_run=true`、`execute=false`、candidate、
digest-pinned imageを確認した。外部repository_dispatch、Gateway run、副作用なしのremote確認は未実施。

### Unit 2: execute dispatch

Unit 1のplanを人手review後、同じlogical request IDで`dry_run=false`、`execute=true`を
dispatchする。execution IDはGateway生成値を使用し、planのIDを再利用しない。

受入れ状態: `BLOCKED / NOT RUN`。HF computeと外部callbackを発生させるため、明示実行承認と
必要な権限確認が必要。

### Unit 3: completion・lifecycle・ACK

completion receipt、lifecycle artifact、HF Jobs result、source ACKを次のキーで突合する。

```text
source_repository
receipt_repository
hf_bucket
candidate_id
candidate_content_digest
image_ref / image_digest
suite / executor / environment
request_id / request_execution_id
```

受入れ状態: `NOT VERIFIED`。実run、completion、ACKが存在しない。

### Unit 4: #154 close判断

public external/provider evidenceとprivate trusted package evidenceを分離したclose reportを
作成する。public証跡をprivate artifactへ昇格せず、trusted private builderのrepository、
workflow、event、branch、head SHA、artifact SHA、run/attemptを別途確認する。

受入れ状態: `OPEN`。reviewerによるclose判断が残っている。

## 検証境界

| 証拠レベル | 今回確認した範囲 | 未確認範囲 |
|---|---|---|
| Source/static | workflow、docs、schema、固定identity | remote default-branch SHAの再取得 |
| Unit/contract | 既存normalize/receipt/ACK/lifecycle契約 | 固定payloadのpublic remote受理 |
| External/provider | なし | Gateway、HF Jobs、completion、ACK |
| Private trusted acceptance | なし | private builder artifactと#154 close条件 |

## 実装・検証順序

1. Unit 0の固定identity・権限表を再確認する。
2. 固定payloadのlocal normalizationとschema/identity negative testを実行する。
3. `dry_run=true/execute=false`のpublic dispatchを実行し、remote副作用なしを確認する。
4. 人手review後、同じlogical request IDで`dry_run=false/execute=true`を実行する。
5. Gateway/V2/HF Jobs/completion/lifecycle/ACKをexecution identityで突合する。
6. external evidence reportを作成し、private trusted evidenceと分離して#154 close判断へ渡す。

## 安全境界

- token値をログ、payload、artifact、commit、summaryへ出力しない。
- plan-onlyでcandidate download、build、evaluation、HF Jobsを起動しない。
- HTTP 204、workflow dispatch受付、HF Jobs起動だけを成功扱いしない。
- provider未実行、callback欠落、identity mismatchを推測で補完しない。
- private Actions artifactをpublic証跡から生成・偽装・再署名しない。

## 着手時点の次アクション

次の安全な作業は、external writeを伴わないlocal contract検証である。local検証がPASSした
後も、public dispatchは別のexternal actionとして扱い、Unit 1のplan-onlyから開始する。

Unit 1のlocal wrapperは`scripts/ci/dispatch-public-inspection-bypass.sh`である。

Unit 2 execute記録 (2026-08-20): Gateway run `32330498316`はresolve・dispatchともPASSし、
V2 run `32330542209`まで到達した。legacy candidate `ctc/candidate-000001`の5ファイルを
取得したが`metadata.json`が0 byteでcandidate contract違反となりmaterializeを拒否した。
HF Jobs実推論は未起動、completion receipt dispatchも対象private repositoryへのHTTP 404で
失敗した。空metadataの生成は行わず、Unit 2は`BLOCKED / INVALID CANDIDATE ARTIFACT`とする。

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

`plan`/`execute`のpayloadを固定値から生成し、`--print`で外部writeなしに確認できる。
