# Recursive Delivery Entry: RTF Benchmark completion

作成日: 2026-08-21
対象branch: `codex/rtf-benchmark-completion-docs`
起点: `main` at `4937ee4`
目的: GitHub Actionsで実行するRTF BenchmarkのGHCR、Resolver、provider実行、record生成、`asr-rtf-rank`、成果PRまでの一連の契約を完成させる。

## Branch purpose

このbranchは、RTF Benchmarkの関連仕様とActionsの想定動作を一つの実装・受入単位として整理するためのbranchである。対象は、既存workflowの挙動を現行仕様に合わせて接続し、未接続または未検証の境界を明示することとする。

この初期commitでは、実GPUサービスを起動せず、フロー設計、契約、実装順序、受入条件を文書化する。GHCR push、HF fixture mutation、RunPod/HF Jobs実行、ranking成果PRの自動生成は、このbranchのcommit操作では実行しない。

## Scope

- digest-pinned GHCR benchmark imageのbuild/publish/audit/evaluate境界
- RTF Resolverによる固定dataset/audio manifestとfixture revisionの生成
- `RTF Benchmark Run`によるbatch 1/8/32実行とprovider receipt収集
- `RTF Service Result`によるresult/metrics SHA、schema、provider proof検証
- `build-rtf-benchmark-record.py`によるranking入力recordへの変換
- 既存Rust `asr-rtf-rank`のCLI契約と`benchmark-ranking.yml`接続
- `rtf-scores/`の成果物構造、bot branch/PR、重複・blocked扱い
- Phase 1 / Fullの移行と残作業
- DirectML retired境界の明示

## Out of scope

- 実モデル・大容量音声・tensor・Docker layerのcommit
- HF_TOKEN/RUNPOD_TOKENの取得・表示・保存
- 実GHCR packageの変更、HF Dataset fixtureのremote mutation
- 実GPU providerの実行成功をローカルで偽装すること
- DirectMLの新規実装・受入経路への復帰

## Dependency-ordered units

```text
Unit 0: branch / authority / acceptance freeze
  -> Unit 1: GHCR image identity contract
  -> Unit 2: Resolver manifest and fixture contract
  -> Unit 3: provider run and receipt contract
  -> Unit 4: benchmark record promotion contract
  -> Unit 5: asr-rtf-rank Actions integration
  -> Unit 6: Phase 1/Full completion and external proof
```

各UnitはOrient → Define → Prove → Implement → Verify → Acceptの順に処理する。contract testを通過しただけで外部providerの実測成功とはみなさない。

## Current evidence

- `docker/rtf-benchmark/`、固定依存lock、runner、entrypointは存在する。
- `ghcr-build-publish.yml`はDockerfile labelからpackageをdiscoverし、mainでpush、digest取得、attestation、build provenance artifactを行う。
- `rtf-resolver.yml`はdigest固定image内でCommon Voice revisionを解決し、materialized audio、manifest SHA、fixture revisionを生成する。
- `rtf-benchmark-run.yml`はbatch 1/8/32を実行し、provider receiptを`rtf-service-result.yml`へ渡す。
- `asr-rtf-rank`はRust binaryとして存在し、valid completed recordのみをcost/CER/RTF等で決定的にsortする。
- `benchmark-ranking.yml`はranking JSON/Markdownを生成し、inspection branchからmain向けPRを作成する想定である。
- `rtf-benchmark-contracts.yml`はworkflow syntax、matrix、Docker provider path、Rust contractを検査する。

## Completion blockers

- 実GHCR digestがcanonical benchmark inputとして発行・audit済みであること。
- Resolverが固定dataset revisionとmaterialized audioを実行し、fixture repositoryのimmutable revisionを返すこと。
- HF/RunPodの実GPU実行でprovider execution proof、metrics URI、result/metrics SHAを取得すること。
- completed recordが必要なRTF、CER、GPU、料金、manifest/image identityを備えること。
- ranking workflowが実record群から再現可能なrankingと成果PRを作成すること。
- Full測定はPhase 1のaccepted summaryからのみ開始すること。

## Rollback

失敗時は結果を`blocked`/`not_verified`として保持し、成功recordやrankingへ昇格させない。既存の`rtf-scores`履歴、HF fixture、external artifactを上書きしない。workflow変更はcontract testが失敗した状態でmainへ反映しない。

## Next safe unit

Unit 1として、GHCR build provenanceのdigest、label、attestation、`ghcr-evaluate`のpull identityが同じbenchmark inputへ結び付くことをcontract化する。
