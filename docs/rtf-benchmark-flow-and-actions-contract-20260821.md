# RTF Benchmark Flow and GitHub Actions Contract

作成日: 2026-08-21
対象: `nvidia/parakeet-tdt_ctc-0.6b-ja`を含むRTF Benchmark workflow群
正本branch: `codex/rtf-benchmark-completion-docs`
関連entry: [`recursive-delivery-entry-rtf-benchmark-completion-20260821.md`](./recursive-delivery-entry-rtf-benchmark-completion-20260821.md)

## 1. Canonical flow

```text
source-controlled Dockerfile
  -> GHCR Build and Publish
  -> image digest + labels + attestation
  -> RTF Resolver
  -> fixed dataset/audio manifest + fixture revision
  -> RTF Benchmark Run
  -> HF Jobs or RunPod Pod provider execution
  -> result/metrics URI + SHA-256 + provider receipt
  -> RTF Service Result
  -> benchmark-record.json
  -> asr-rtf-rank
  -> ranking.json / ranking.md
  -> inspection branch + main PR
```

`resolve-target`やGHCR tag解決はmetadata resolutionであり、digest、manifest、provider proofが揃うまでexecution readinessを意味しない。

## 2. GHCR build contract

Authority: `.github/workflows/ghcr-build-publish.yml`, `docs/ghcr-ci.md`, `docker/rtf-benchmark/`.

参加Dockerfileは次のlabelを持つ。

```dockerfile
LABEL io.jpapt.source.repo_id="..."
LABEL io.jpapt.source.framework="..."
LABEL io.jpapt.ghcr.package="..."
LABEL io.jpapt.role="..."
```

PRではBuildx buildとDockerfile内import/version smokeを実行するが、push/loadは行わない。main/manualではGHCRへpushし、返却された`sha256:<digest>`を検証し、attestationとbuild provenance artifactを保存する。

実行側は`:latest`やgit SHA tagを実験identityに使わず、必ず次の形へfreezeする。

```text
ghcr.io/<owner>/<package>@sha256:<digest>
```

必要なidentityはimage reference、digest、Dockerfile/context、source repo、role、Git commitであり、tokenやcandidate payloadをimage layerへ入れてはならない。

## 3. GHCR publish to RTF Resolver chain

`.github/workflows/ghcr-build-publish.yml`のmain push/manual実行では、全Docker build matrix完了後にcanonical `parakeet-rtf-benchmark` build provenance artifactを取得し、`published=true`、`role=rtf-benchmark`、digest-pinned referenceを検証する。そのexact image referenceをreusable `.github/workflows/rtf-resolver.yml`へ渡してResolverを連続実行する。

PR buildではGHCR publishを行わないため、RTF Resolverは連続実行しない。Resolverのmanual実行ではimage inputを空にして最新digest解決を選択できるが、GHCR chainでは必ずbuild jobが発行したdigestを使用する。

## 4. RTF Resolver contract

Authority: `.github/workflows/rtf-resolver.yml`, `docker/rtf-benchmark/benchmark-runner/benchmark_runner/resolve_dataset.py`.

Resolverは次を固定する。

- dataset: `japanese-asr/ja_asr.common_voice_8_0`
- dataset revision: workflow inputのimmutable commit
- configuration/split: `default` / `test`
- deterministic seed: `rtf-benchmark-v1-common-voice-ja`
- inspection profile: `smoke`、`pref`、または`probe`
- audio contract: float32, mono, 16000 Hz, finite, C-contiguous, materialized file
- manifest SHA-256、dataset revision、fixture repository revision、image digest

Resolverの成果物は少なくとも次である。

```text
rtf-scores/benchmark/benchmark-v1.jsonl
rtf-scores/benchmark/benchmark-v1.jsonl.sha256
rtf-scores/benchmark/benchmark-v1.receipt.json
rtf-scores/benchmark/benchmark-v1.fixture.json
```

fixture upload成功はbenchmark実行成功ではない。fixture revisionとmanifest SHAが次のrunへ入力されることを確認する。

## 5. Provider execution contract

Authority: `.github/workflows/rtf-benchmark-run.yml`, `scripts/run-benchmark.sh`, `rtf-service-result.yml`.

現行Phase 1 matrixは次の6組である。

| service | GPU |
|---|---|
| HF Inference/HF Jobs lane | T4, L4 |
| RunPod Pod lane | A5000, L4, RTX 3090, RTX 4090 |

実行はbatch 1/8/32を一回のworkflowで処理し、repeatはrunner側で管理する。batch sizeをworkflow inputで一つだけ選択して比較条件を変えてはならない。

providerは次をreceiptへ返す。

```text
run_id
status: completed | blocked | not_verified
job_id
result_uri / result_sha256
metrics_uri / metrics_sha256
error_code / error_message
```

`completed`ではjob identity、result、metrics、SHAが全て必要である。CPU fallback、provider registration、job submissionだけではGPU execution proofにならない。

DirectMLは2026-08-20付でretiredであり、新規workflow、dispatch、receipt、HF Jobs、Bucket completion claimのactive routeに含めない。既存artifactはhistorical audit onlyとする。

DirectMLのactive workflow、provider strict probe、Windows candidate evaluation、runtime provider feature、provider configurationは削除済みである。旧receipt/protocol fieldおよび監査文書に残る名称は、過去artifactの識別用であり、実行routeを表さない。

実runの結果は[RTF Benchmark GitHub Actions実run証拠](./rtf-benchmark-action-run-evidence-20260821.md)に固定する。

## 5. Result-to-record contract

`rtf-service-result.yml`はURIからresult/metricsを取得し、SHA-256、schema、manifest、image digest、provider identityを検証する。`scripts/ci/build-rtf-benchmark-record.py`は検証済みmetricsを`benchmark-record.json`へ変換する。

ranking対象recordは次を満たす必要がある。

- schema valid
- `status=completed`
- provider execution proof true
- valid RTF/RTFx and CER
- GPU identity and provider boundary present
- cost data present when cost ranking is requested
- fixed dataset/manifest identity present
- digest-pinned image identity present
- result/metrics SHA-256 verified

不足recordはrankingから除外するが、理由を失わずblocked/not_verifiedとして保存する。

## 6. `asr-rtf-rank` contract

Current implementation: `rust/crates/asr-contracts/src/bin/asr-rtf-rank.rs`.

CLI:

```text
asr-rtf-rank <output.json> <record.json>...
```

ranking workflowでは`--phase phase1|full`を指定し、Rustがrecord間identity、重複、
accepted recordの有無を検証する。除外されたblocked/未計測recordの理由は
`rtf-scores/ranking-exclusions.json`へ保存する。

処理は各入力recordをRust schema validatorで検証し、completedかつprovider execution proof、CER、costが揃ったrecordだけを採用する。sort keyは次の順で固定する。

```text
cost_per_audio_hour
cer
rtf
service_id
gpu
batch_size
run_id
```

出力は`{"schema_version":1,"records":[...]}`のdeterministic JSONである。今後の完成作業では、recordのglob収集、phase/profile identity、manifest/image digest一致、duplicate run拒否、Markdown生成をCLIまたはActions側で二重実装せず、Rust contractを正本として結合する。

## 7. Ranking Actions contract

Authority: `.github/workflows/benchmark-ranking.yml`.

workflowはmanual dispatchの`phase=smoke|pref|probe`を受け、`rtf-scores/<phase>/`から`benchmark-record.json`をsorted globで収集する。recordが0件ならBLOCKEDとして終了する。

完成時の処理順は次のとおり。

1. record pathを安定順で列挙
2. Rust validatorで全recordを検証
3. phase、manifest SHA、image digest、provider boundaryをcross-check
4. accepted recordだけを`asr-rtf-rank`へ渡す
5. `rtf-scores/ranking.json`と`ranking.md`を生成
6. 差分がある場合だけ`inspection/rtf-benchmark-ranking-<phase>`へcommit/push
7. 同branchの既存PRを再利用し、なければmain向けPRを作成

ranking workflowが生成するcommitはbenchmark成果のみを含める。workflow source、履歴回収artifact、未検証recordをranking commitへ混在させない。

## 8. Phase 1 / Full transition

Phase 1は固定subset、batch 1/8/32、provider/GPU matrixの比較可能性を確保する。FullはPhase 1のaccepted summaryから上位候補を機械的に選び、同じimage digest、dataset revision、計算式を再利用する。

Phase 1が失敗またはcandidate selection不能の場合、Fullは起動しない。FullはPhase 1を上書きせず、別profile/別成果として保存する。

## 9. Actions secrets and external evidence

```text
HF_TOKEN      -> HF dataset/fixture/endpoint boundary only
RUNPOD_TOKEN  -> RunPod boundary only
github.token  -> GHCR/package/contents/PR permissions as declared
```

secret valueはlogs、Docker layer、metrics、Git artifactへ書き出さない。外部serviceの成功状態は、run ID、job ID、URI、digest、SHA、revisionが揃って初めて本リポジトリのrecordへ変換できる。

## 10. Completion checklist

- [ ] GHCR image build/publish/audit/evaluateが同一digest identityで接続されている
- [ ] Resolverが固定manifest、materialized audio、fixture revisionを生成する
- [ ] Benchmark Runがbatch 1/8/32を実行し、全batchのblockedを失敗扱いにする
- [ ] provider receiptがresult/metrics SHAとexecution proofを持つ
- [ ] record builderがschema-valid immutable benchmark recordを生成する
- [ ] `asr-rtf-rank`がrecord identityとphaseを検証してrankingする
- [ ] ranking Actionsがempty/duplicate/mismatchをrejectする
- [ ] ranking JSON/Markdownをinspection branchからmain PRへ保存する
- [ ] Phase 1 accepted後だけFullへ進む
- [ ] DirectMLがactive routeへ混入していない
- [ ] 実GPU外部証拠をlocal contract testと分離して記録する

## 11. Verification commands

```text
cargo fmt --all -- --check
cargo check --locked --workspace
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
uv lock --check
mise run doctor
git diff --check
```

実GPU、GHCR remote object、HF fixture remote revision、RunPod/HF Jobs credential境界は外部証拠として別途受入する。
