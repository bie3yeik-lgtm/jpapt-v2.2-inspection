# Recursive Delivery Entry: RTF Benchmark Reconstruction

## Purpose and approved scope

`docs/rtf-benchmark-implementation-plan.md`を、履歴保存ではなく再現可能なRTF benchmark成果へ実装する。Phase 1はHF Inference EndpointのT4/L4とRunPod PodのA5000/L4/RTX 3090/RTX 4090を対象とし、実GPU実測は外部credentialとprovider availabilityがある場合だけ実行する。

## Unit 1: benchmark record contract

`evaluation/schemas/rtf-benchmark-record.schema.json`を追加し、provider metricsからランキング対象recordへ昇格するための固定identityを定義した。Rust `validate_rtf_benchmark_record`はcompleted recordのprovider execution proof、CER、GPU価格を必須とし、未検証結果をランキング可能なcompletedとして通さない。

## Unit 2: dataset, credential, and image decisions

Phase 1のdatasetは`japanese-asr/ja_asr.common_voice_8_0`に固定する。dataset revision、resolved manifest、materialized audio SHA-256をrun identityへbindし、毎回のrandom抽出は行わない。HF Inference EndpointはRepository secret `HF_TOKEN`、RunPod PodはRepository secret `RUNPOD_TOKEN`を使用する。secretはWorkflowのenv境界だけで扱い、ログ、Dockerfile、image layer、metrics、Gitへ書き出さない。

共通imageは`docker/rtf-benchmark/`へ作成する。Dockerfile、依存lock、runner、entrypoint、README、`.dockerignore`をこのディレクトリへ置き、build後にGHCR digestをimmutableなbenchmark inputとして固定する。tagや`latest`はrecordのidentityに使用しない。

## Verification and boundary

```text
schema JSON parse: PASS
focused Rust contract test: PASS (5 tests)
external GPU/provider execution: NOT VERIFIED
HF Bucket upload/read-back: NOT VERIFIED
```

## Unit 2: common Docker image

`docker/rtf-benchmark/`を追加した。base imageは既存の
`nvcr.io/nvidia/nemo-speech:26.07.00`に固定し、依存lock、Dockerfile、entrypoint、
manifest contract runner、README、`.dockerignore`を配置した。runnerは現在、resolved
manifestのmaterialized local audio、duration、manifest SHA-256を検証し、model-specific
inference未接続を`BENCHMARK_INFERENCE_NOT_IMPLEMENTED`として`blocked`で出力する。
contract validationをcompleted benchmarkへ昇格させないfail-closed境界である。

`benchmark-build.yml`はGHCRへimageをpushし、registryから取得したimmutable digestを
image metadata Artifactへ保存する。HF/RunPod secretsはimage buildへ渡さない。

```text
Python compileall: PASS
manifest runner smoke: PASS (explicit BLOCKED)
Docker CLI/build: NOT VERIFIED (docker unavailable on this host)
GHCR push/digest: NOT VERIFIED
provider inference: NOT VERIFIED
```

## Next unit

次は`japanese-asr/ja_asr.common_voice_8_0`のfixed revision lockとresolved manifestを追加し、同じ入力manifestを全providerへ渡せる状態にする。その後、model-specific inference runnerとPhase 1 provider adapterへ進む。
