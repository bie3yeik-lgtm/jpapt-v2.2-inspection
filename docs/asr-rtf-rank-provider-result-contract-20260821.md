# asr-rtf-rank provider result contract

更新日: 2026-08-21
状態: provider result / metrics受領とranking入力の正本
対象: `asr-rtf-rank`、HF Jobs、RunPod Pod、`rtf-service-result.yml`

## 1. 目的と正本範囲

この文書は、HF JobsまたはRunPod Podで得られたresult/metricsを、
`asr-rtf-rank`が比較可能なranking recordとして受領するための実装契約である。
ランキング値の計算式だけでなく、remote execution、fixture、model、dataset、image、
result URI、SHA-256の同一性を受入条件に含める。

正本の優先順位は次のとおりとする。

1. `evaluation/schemas/rtf-service-metrics.schema.json`
2. `evaluation/schemas/rtf-service-result.schema.json`
3. `evaluation/schemas/rtf-benchmark-record.schema.json`
4. Rust `asr-rtf-rank` / `asr-contracts` validator
5. `.github/workflows/rtf-service-result.yml` と `benchmark-ranking.yml`
6. provider adapterのlogとActions artifact

workflowやMarkdownはrankingの意味を独自定義してはならない。

## 2. providerから受け取る段階

```text
provider allocation
  -> image/container ready
  -> fixture download and manifest SHA verification
  -> model download at immutable revision
  -> content probe
  -> GPU/provider execution proof
  -> metrics generation
  -> result/metrics upload
  -> immutable URI and SHA receipt
  -> service-result validation
  -> benchmark-record validation
  -> asr-rtf-rank
```

`result/metrics`だけを取得できても、provider上で実行された証拠がなければrankingへ
投入してはならない。GHCR digest、HF fixture revision、dataset/model revision、
manifest SHAは同一runの全artifactで一致する必要がある。

## 3. HF Jobs契約

HF Jobsは次の情報を受領する。

```json
{
  "service_id": "hf-jobs",
  "job_id": "provider job id",
  "job_url": "https://huggingface.co/jobs/...",
  "status": "completed|blocked|not_verified",
  "image_digest": "sha256:...",
  "model_id": "...",
  "model_revision": "40-hex revision",
  "fixture_repo_id": "gawohok7/rtf-benchmark-fixtures",
  "fixture_revision": "40-hex revision",
  "manifest_sha256": "64-hex",
  "content_probe": "completed|blocked",
  "metrics_uri": "immutable HF Dataset URI",
  "metrics_sha256": "64-hex"
}
```

HF Jobの既定timeoutは30分であるため、workflowのtimeoutとは別に`--timeout`を明示する。
image pull、fixture/model download、content probe、full inferenceを同じremote timeout
budget内で扱う。Job ID、terminal status、log、resource statsをActions artifactへ保存し、
receipt lineがない場合もremote failureを`PROVIDER_EXECUTION_FAILED`へ潰さない。

参照: [HF Jobs](https://huggingface.co/docs/huggingface_hub/guides/jobs)、
[HF CLI timeout](https://huggingface.co/docs/huggingface_hub/en/guides/cli)

## 4. RunPod Pod契約

RunPodではPod ID、Pod state、container state、SSH reachabilityを別々に受領する。
`pod create`成功やPod ID取得は、image pull完了・container起動・推論実行の証拠ではない。

```json
{
  "service_id": "runpod-pod",
  "pod_id": "provider pod id",
  "pod_state": "...",
  "container_state": "...",
  "ssh_ready": true,
  "image_digest": "sha256:...",
  "registry_auth_id": "configured registry credential id",
  "fixture_revision": "40-hex revision",
  "manifest_sha256": "64-hex",
  "content_probe": "completed|blocked",
  "metrics_uri": "immutable HF Dataset URI",
  "metrics_sha256": "64-hex"
}
```

private GHCR imageを使う場合は`--registry-auth-id`を明示する。
実際にActionsで使用したrunpodctl v2.11.0では`--terminate-after`がGraphQL
`DateTime`として検証されるため、durationではなくUTC timestamp（例:
`2026-08-23T12:00:00Z`）を渡す。readinessは`pod get`のruntime状態をpollし、CLIの単一blocking waitへ依存しない。
SSH失敗やPod早期終了の場合は、削除前にPod inspect、create response、container state、
last logsをActions artifactへ保存する。

参照: [RunPod runpodctl pod](https://docs.runpod.io/runpodctl/reference/runpodctl-pod)

## 5. result/metrics受入契約

completed受入には以下をすべて要求する。

- `status=completed`
- `job_id`または`pod_id`が存在する
- `content.json.status=completed`かつ`content_available=true`
- provider execution evidenceが存在する
- metrics schemaがvalid
- result URIとmetrics URIが同一
- result SHA-256とmetrics SHA-256が同一
- remote取得したmetricsのSHA-256がreceiptと一致する
- run_id、service_id、provider、environment、GPU、batch size、profileが一致する
- model revision、dataset revision、fixture revision、manifest SHA、image digestが一致する
- RTF、RTFx、audio duration、processing durationが正数
- rankingでCERまたは採用する品質metricが存在する
- cost rankingを行う場合はcost値が存在する

不足時の分類は次のとおりとする。

```text
PROVIDER_IDENTITY_MISSING
PROVIDER_EXECUTION_UNPROVEN
CONTENT_PROBE_MISSING
METRICS_URI_MISMATCH
METRICS_SHA256_MISMATCH
METRICS_IDENTITY_MISMATCH
FIXTURE_REVISION_MISMATCH
MANIFEST_SHA256_MISMATCH
IMAGE_DIGEST_MISMATCH
QUALITY_METRIC_MISSING
COST_METRIC_MISSING
```

blocked/not_verifiedはranking対象から除外するが、理由とprovider evidenceは保存する。

## 6. `asr-rtf-rank`の現行挙動と不足

実装正本は`rust/crates/asr-contracts/src/bin/asr-rtf-rank.rs`である。

現行CLI:

```text
asr-rtf-rank <output.json> <record.json>...
```

追加オプション:

```text
asr-rtf-rank <output.json> --phase <phase1|full> \
  --diagnostics <excluded.json> <record.json>...
```

現行実装は各recordのschemaを検証し、次の条件を満たすものだけをsort対象にする。

```text
status == completed
provider_execution_proof == true
cost_per_audio_hour != null
cer != null
```

sort順は次のとおりである。

```text
cost_per_audio_hour
cer
rtf
service_id
gpu
batch_size
run_id
```

しかし、現行実装には次の不足がある。

1. `provider_execution_proof`がremote job/pod evidenceを参照していない。
2. record間のmodel、fixture、manifest、image identityをcross-checkしていない。
3. 同一run_id、同一service/GPU/batchの重複を拒否していない。
4. phase/profileの混在を拒否していない。
5. record間の共通identityをcross-checkし、混在時はrankingをfailする。
6. 同一run/service/GPU/batchの重複を拒否する。
7. 全recordが除外された場合は非zeroで終了する。
8. CER/cost/status/execution proofによる除外理由をdiagnosticsへ保存する。

なお、現在のResolver生成manifestは21件すべての`text`が空白文字であり、現行runnerでは
CERがnullになる。したがって、このfixture状態ではcost/CER rankingのaccepted inputは成立しない。

## 7. 実装資料: Recursive Units

### Unit 1 — provider execution envelope

`service-result`にprovider stage、remote ID、image/fixture/manifest identity、
content probe status、diagnostic artifact URIを追加する。

受入: HF JobsとRunPodのblocked fixtureが、receipt無しでもtyped failureとして保存される。

### Unit 2 — result/metrics identity verifier

Rust側でreceipt、metrics、content probe、benchmark recordのidentityを検証する。
Pythonの`build-rtf-benchmark-record.py`は変換境界に限定し、production validatorを二重化しない。

受入: SHA、URI、run、provider、GPU、batch、revision不一致が全てfailする。

### Unit 3 — remote execution proof binding

`provider_execution_proof`を単なる`provider=cuda`判定から、次の証拠の一致判定へ変更する。

```text
remote job/pod identity
  + container start evidence
  + content probe completed
  + metrics generated in the same run
  + immutable result upload
```

### Unit 4 — rank input set validation

ranking前に全recordの次をcross-checkする。

```text
phase/profile
model_id/revision
dataset_id/revision
fixture_repo_id/revision
manifest_sha256
image_digest
decoder/precision
```

不一致、重複、空入力はrankingをblockedにする。

### Unit 5 — deterministic ranking output

`asr-rtf-rank`はaccepted recordだけでなく、除外recordと除外理由を別のdiagnostic outputへ
保存する。ranking JSONが空の場合はexit 2とし、MarkdownやPRを生成しない。

`rtf-scores/<profile>`配下を再帰的に走査し、同一の`service_id`、`gpu`、`batch_size`に対して複数のrecordが存在する場合は、
blocked/not_verifiedを候補にせず、completedかつCER・cost・provider execution proofを満たす
recordだけを候補にする。その候補のうち`completed_at`が最も新しいrecordをrankingへ採用する。
`completed_at`がない旧recordは`run_id`を後方互換のrecency keyとして扱う。採用されなかった
古いcompleted recordは`ranking-exclusions.json`へ`superseded`理由で保存する。

さらに、recordと同じディレクトリにある`metrics.json`を必須のmetrics sidecarとし、
recordの`metrics_sha256`との一致、JSON object、`status=completed`を確認できないrecordは
ranking候補から除外する。除外理由は`ranking-exclusions.json`へ保存する。これにより、
RunPodの新しいblocked/not_verified試行が、過去の有効なmetricsを隠すことを防ぐ。

### Unit 6 — Actions integration

`benchmark-ranking.yml`は以下の順序に固定する。

1. record pathを安定順で収集
2. Rust identity validatorを実行
3. duplicate/mismatch/emptyをreject
4. accepted recordだけを`asr-rtf-rank`へ入力
5. Rustがranking JSONと除外diagnosticsを生成し、空入力を拒否
6. Markdown生成
7. 差分がある場合だけ成果PRを作成

## 8. 現在の受入判定

直近runではResolverは成功していますが、HF JobsはCUDA illegal memory access/OOM、
RunPodはSSH/container readinessで停止しています。そのため、現時点で
`asr-rtf-rank`へ渡せるaccepted provider resultはありません。

参照:

- [RTF Resolver #32414089663](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32414089663)
- [RTF Benchmark Run #32414647326](https://github.com/bie3yeik-lgtm/jpapt-v2.2-inspection/actions/runs/32414647326)
- [RTF provider investigation](./rtf-provider-service-investigation-20260821.md)

## 9. 完了条件

- HF Jobs/RunPodのremote identityがreceiptへ保存される
- image pull、fixture/model download、content probe、inferenceのstageが識別できる
- result/metricsのURIとSHAが検証される
- provider execution proofがremote evidenceへbindされる
- record間のrevision/image/manifest identityが一致する
- duplicate、empty、partial、CER欠落をrankingへ流さない
- `asr-rtf-rank`の空rankingを成功扱いしない
- ranking JSON/Markdownはaccepted recordだけから生成される
- 実HF/RunPod runで上記証拠が確認される

この文書がprovider result受領と`asr-rtf-rank`結合の実装正本であり、既存の概要資料はこの契約に従って更新する。
