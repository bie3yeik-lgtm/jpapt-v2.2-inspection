# RTF local provider adapter test

更新日: 2026-08-21

## 目的

GitHub Actionsで外部providerを起動する前に、RTF benchmark Dockerfile、entrypoint、
HF Jobs adapter、RunPod adapter、content/receipt回収経路をローカルで検証する。

既定のmock testはHF JobやRunPod Podを作成しない。fake CLIがproviderのmachine-readable
content/receiptを返し、`scripts/run-benchmark.sh`が同じローカルartifactを回収できることを
確認する。

## 実行方法

```bash
# Dockerfile、schema、entrypoint、adapterの静的検証だけ
bash scripts/ci/test-rtf-provider-adapters.sh --mode static

# HF Jobs/RunPodのCLI hand-offをfake CLIで検証（外部リソースなし）
bash scripts/ci/test-rtf-provider-adapters.sh --mode mock

# Dockerfileを実際にlocal imageへbuild（時間がかかるため通常のチェックからは除外）
# 必要な受入段階で明示的に実行する
bash scripts/ci/test-rtf-provider-adapters.sh --mode docker \
  --image parakeet-rtf-benchmark:local

# 実providerを明示的に起動する場合のみ
RTF_IMAGE_DIGEST=sha256:<digest> \
HF_TOKEN=... \
bash scripts/ci/test-rtf-provider-adapters.sh \
  --mode live --provider hf --allow-external
```

`--mode live`はHF JobまたはRunPod Podを作成し、課金・外部状態変更を発生させる。
`--allow-external`がない場合は実行しない。RunPodでは`RUNPOD_TOKEN`も必要である。

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
検証できる。
