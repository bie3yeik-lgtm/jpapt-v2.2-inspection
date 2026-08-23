# RTF local provider adapter test

更新日: 2026-08-21

## 目的

GitHub Actionsで外部providerを起動する前に、RTF benchmark Dockerfile、entrypoint、
HF Jobs adapter、RunPod adapter、content/receipt回収経路をローカルで検証する。

既定のmock testはHF JobやRunPod Podを作成しない。fake CLIがproviderのmachine-readable
content/receiptを返し、`scripts/run-benchmark.sh`が同じローカルartifactを回収できることを
確認する。

## 実行方法

### 無課金の環境preflight

`.env`を自動実行せず、単純な`KEY=value`だけを読み込みます。`RUNPOD_API`は
ローカル互換aliasとして`RUNPOD_TOKEN`へ変換します。HF Job、RunPod Pod、Docker
pull、ネットワークAPIは呼び出しません。

```bash
# WSL login shell supplies the mise/HF CLI PATH on this Windows workspace.
bash -lc 'cd /mnt/k/workspace/jpapt-v2.2-inspection && bash scripts/ci/rtf-local-preflight.sh --provider all'
```

Actionsの正本名は`RUNPOD_TOKEN`です。`.env`でも同じ名前を使うことを推奨します。

## ローカル`.env`の不足項目チェック

現在の`.env`に`HF_TOKEN`と`RUNPOD_API`があれば、mockによる無課金のadapter検証は実行できます。
ただし、実providerを起動するdry-run相当の事前検証（外部APIへ接続するがPod/Jobを作らない
確認を含む）と、実provider起動には次の境界があります。

| 項目 | 必須段階 | 用途 | 現在の扱い |
|---|---|---|---|
| `HF_TOKEN` | HF live | HF Job作成とprivate Hub参照 | `.env`に追加済み。値は表示・commitしない |
| `RUNPOD_TOKEN` | RunPod live | runpodctl API/SSH key同期 | Actionsの正本名。`RUNPOD_API`はローカルaliasとして補完 |
| `RUNPOD_API` | ローカル互換 | `RUNPOD_TOKEN`未設定時の入力alias | 追加済み。canonical名への移行を推奨 |
| `RTF_IMAGE_DIGEST` | live launch | GHCR imageのimmutable digest | 未設定ならpreflightは警告、launchは停止 |
| model/dataset/fixture revision | live launch | 再現可能なidentity固定 | `.env.example`のplaceholderを実値へ置換 |
| `RTF_FIXTURE_MANIFEST_SHA256` | live launch | fixtureとrunの一致検証 | 未設定なら既存workflowの解決結果を使う場合を除き停止 |
| `hf`, `runpodctl`, `jq` | static/mock/live wrapper | CLIとJSON回収 | WSL login shellで確認済み |
| Docker/driver/GPU | docker/live execution | image buildまたは実推論 | static/mockでは不要。外部実験前に別途確認 |

したがって、現時点で追加の秘密値は不要です。実providerを安全に起動する前に必要なのは、
`RUNPOD_API`を`RUNPOD_TOKEN`へ整理すること、`RTF_IMAGE_DIGEST`とrevision群を実値で埋めること、
およびWSLのCLI存在・versionを確認することです。`.env`は`.gitignore`対象であり、GitHub Actions
へは渡さず、ActionsではRepository Secret（`HF_TOKEN`/`RUNPOD_TOKEN`）を使用します。

現環境の注意点:

- このWindows workspaceでは、WSL login shellに`hf`、`runpodctl`、`jq`が存在する。
  PowerShell側の`jq`は未導入なので、preflightとadapter wrapperはWSLで実行する。
- 現在のWSL CLIは`hf 1.27.0`、`runpodctl 2.9.0`、`jq 1.8.1`である。GitHub Actionsは
  RunPod CLIを別途installし、HF clientもupgradeするため、live受入前にバージョン差を
  解消またはログへ記録する。
- `RTF_IMAGE_DIGEST`が未設定の場合、preflightは警告で終了するが、provider launchは
  digest固定を要求して停止する。

## 2026-08-23 `.env`追加後の不足項目監査

`.env`のキー名だけを確認した結果、現在は`HF_TOKEN`、`RUNPOD_API`、
`CR_PAT`、`GITHUB_PAT_TOKEN`、`GITHUB_CLASSIC_TOKEN`が存在する。値はログ、文書、
Gitへ出力しない。

`HF_TOKEN`と`RUNPOD_API`だけで十分なのは、providerを作成しない`static`／`mock`段階
である。実Job／Podを作成しないdry-runでは、これらのtoken自体も不要であり、fake CLI
による契約確認だけを行う。`CR_PAT`もActionsの正本ではなく、ローカルでprivate GHCR
imageをpullするときだけ必要になる。

実provider投入前、または実imageを使うローカル境界試験には、次の値が別途必要である。

| 区分 | 必須入力 | 用途 |
|---|---|---|
| image identity | `RTF_IMAGE_DIGEST` | `ghcr.io/...@sha256:<64 hex>`の実行環境固定 |
| model identity | `RTF_MODEL_ID`, `RTF_MODEL_REVISION` | modelと40桁revisionの固定 |
| dataset identity | `RTF_DATASET_ID`, `RTF_DATASET_REVISION` | datasetと40桁revisionの固定 |
| fixture identity | `RTF_FIXTURE_REPO_ID`, `RTF_FIXTURE_REVISION`, `RTF_FIXTURE_MANIFEST_SHA256` | Resolverが発行したJSONLとmanifest SHAの固定 |
| run identity | `RTF_RUN_ID`, `RTF_GPU` | provider job/pod名とPhase 1 matrixの選択 |
| local image access | `GHCR_USERNAME`相当のlogin名、`CR_PAT`、Docker login済み状態 | private GHCRをpullする場合のみ |

`RTF_MANIFEST`はfixture repositoryから取得する実行では通常不要で、ローカルに既に
materializeしたJSONLを使う場合だけ指定する。`RTF_BATCH_SIZE`、`RTF_PRECISION`、
`RTF_DECODER`、dataset profile、RunPodのtimeout等は既定値があるが、再現性を重視する
受入試験では明示指定する。

なお、`rtf-local-preflight.sh`は安全のため`.env`を親シェルへexportしない。preflightの
PASS後に別コマンドで`run-benchmark.sh`を呼ぶ場合は、値がそのプロセスへ渡っていることを
確認する必要がある。`.env`をshellとして直接`source`する運用は、任意コマンド実行を
許すため採用しない。ローカル実行時は、allowlist付きの専用wrapperを使う。

```bash
bash scripts/ci/rtf-local-env.sh --env-file .env -- \
  bash scripts/ci/test-rtf-provider-adapters.sh --mode mock
```

このwrapperは`HF_TOKEN`、`RUNPOD_TOKEN`、`RUNPOD_API`、`HF_FLAVOR`、
`RUNPOD_GPU_ID`、`RTF_*`だけを子プロセスへ渡し、`GITHUB_PAT_TOKEN`、
`GITHUB_CLASSIC_TOKEN`、`CR_PAT`などのGitHub/GHCR用値は渡さない。実providerを
起動する`--mode live`は、wrapperを使っても外部状態と課金が発生するため、
`--allow-external`を明示した場合に限る。

監査時点の無課金確認結果は、WSL上で`hf 1.27.0`、`runpodctl 2.9.0-c094cac`、
`jq 1.8.1`を検出し、`bash scripts/ci/rtf-local-preflight.sh --provider all`はPASSした。
ただし`RTF_IMAGE_DIGEST`未設定のため、これはprovider launch可能の証明ではない。

```bash
# Dockerfile、schema、entrypoint、adapterの静的検証だけ
bash scripts/ci/test-rtf-provider-adapters.sh --mode static

# HF Jobs/RunPodのCLI hand-offをfake CLIで検証（外部リソースなし）
bash scripts/ci/test-rtf-provider-adapters.sh --mode mock

# 実provider投入前の入力完全性だけを、外部APIなしで確認
bash scripts/ci/rtf-local-preflight.sh --provider all --require-launch-inputs

# Dockerfileを実際にlocal imageへbuild（時間がかかるため通常のチェックからは除外）
# 必要な受入段階で明示的に実行する
bash scripts/ci/test-rtf-provider-adapters.sh --mode docker \
  --image parakeet-rtf-benchmark:local

# 実providerを明示的に起動する場合のみ（dry-runではなく外部状態・課金が発生）
RTF_IMAGE_DIGEST=sha256:<digest> \
HF_TOKEN=... \
bash scripts/ci/test-rtf-provider-adapters.sh \
  --mode live --provider hf --allow-external
```

`--mode live`はHF JobまたはRunPod Podを作成し、課金・外部状態変更を発生させる。
`--allow-external`がない場合は実行しない。RunPodでは`RUNPOD_TOKEN`も必要である。

## 2026-08-23 継続監査

`.env`の値そのものを表示せず、allowlist wrapper経由で次を確認した。

- `rtf-local-preflight.sh --provider all`: PASS（Job/Pod作成なし）
- `hf auth whoami`: PASS（認証確認のみ）
- `runpodctl doctor --output json`: PASS（Pod作成・課金なし）
- `--require-launch-inputs`: FAIL（意図したfail-closed）

launch inputのFAIL項目は、`RTF_IMAGE_DIGEST`、`RTF_RUN_ID`、model/dataset/fixtureの
各immutable revision、`RTF_FIXTURE_MANIFEST_SHA256`、`RTF_GPU`である。これはtoken不足
ではなく、どのimage・model・dataset・fixtureを実行するかを固定する値が`.env`に未設定
という意味である。これらを推測値やfloating値で補完してはいけない。

この監査ではHF JobもRunPod Podも作成していない。RunPodについては別途、残高不足により
Pod作成前に停止したguarded試行があり、現在のadapterはそれを
`RUNPOD_ACCOUNT_BALANCE_TOO_LOW`として記録する。残高が補充されるまで再試行しない。

## 現在のチェック方針

タスク解消を優先するため、通常のローカルチェックでは`static`と`mock`だけを実行する。
`docker` modeの実image build、GPU container smoke、`live` modeは保留し、必要な受入段階で
明示的に実行する。これらを未実行のままPASSとは扱わない。

## 検証境界

| mode | 検証 | 外部provider |
|---|---|---|
| `static` | Dockerfile label、ENTRYPOINT、schema、shell/python syntax | 使用しない |
| `mock` | HF/RunPod command hand-off、content/receipt回収、identity | 使用しない |
| `docker` | RTF benchmark imageのbuild | base image取得のみ |
| `live` | 実Job/Pod、image pull、fixture/model取得、provider execution | 使用する |

mock PASSは外部サービスの成功を意味しない。実HF/RunPodの受入にはlive実行時のJob/Pod
identity、content probe、metrics、result SHA、provider evidenceが別途必要である。

## CI契約

`rtf-benchmark-contracts.yml`は高速な`--mode mock`を実行する。これによりGitHub Actions自身が
外部providerへ到達できない場合でも、adapterのCLI引数・回収経路・Dockerfile契約をPR時に
検証できる。mockにはRunPod createの無出力ハングを時間短縮して再現し、
`RUNPOD_POD_CREATE_TIMEOUT` receiptを確認するケースも含む。
