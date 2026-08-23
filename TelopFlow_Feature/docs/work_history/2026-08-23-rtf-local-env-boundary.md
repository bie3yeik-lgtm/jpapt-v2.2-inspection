# RTF local provider environment boundary

更新日: 2026-08-23

## 目的と範囲

HF Jobs／RunPodを作成せずに、RTF provider adapterのローカル検証環境を
再現できる状態にする。`.env`の秘密値をGitHub Actions用の値やGHCR用の値と
混在させず、外部実行へ進む前に不足しているimmutable identityを明示する。

## 変更

- `scripts/ci/rtf-local-env.sh`を追加した。
  - 単純な`KEY=value`だけを受け付ける。
  - `HF_TOKEN`、`RUNPOD_TOKEN`、`RUNPOD_API`、`HF_FLAVOR`、`RUNPOD_GPU_ID`、
    `RTF_*`だけをdotenvから子プロセスへ渡す。
  - `GITHUB_*`、`GH_TOKEN`、`CR_PAT`を継承環境からも除外する。
  - `RUNPOD_API`はローカル互換aliasとして`RUNPOD_TOKEN`へ補完する。
- `scripts/ci/test-rtf-provider-adapters.sh`のstatic契約へwrapperを追加した。
- `docs/rtf-local-provider-adapter-test.md`へ安全な実行例と認証境界を追記した。

## 検証結果

WSL login shellで次を実行した。

```text
bash scripts/ci/rtf-local-preflight.sh --provider all
PASS
bash scripts/ci/test-rtf-provider-adapters.sh --mode static
PASS
bash scripts/ci/test-rtf-provider-adapters.sh --mode mock
PASS
```

mockではHF content/receipt回収、RunPod readiness／SSH option、no-instance、
CUDA illegal access、Pod create timeoutを外部リソースなしで確認した。
dotenv wrapper経由の子プロセスでは、HF／RunPod tokenが存在し、GitHub PATと
GHCR PATが存在しないことを値を出力せずに確認した。

## 未検証・ブロッカー

`--require-launch-inputs`は、次のimmutable identityが`.env`に未設定のためFAILする。

- `RTF_IMAGE_DIGEST`
- `RTF_RUN_ID`
- model、dataset、fixtureのIDと40桁revision
- `RTF_FIXTURE_MANIFEST_SHA256`
- `RTF_GPU`

したがって、この変更はローカルadapter環境の成立を示すが、HF Job／RunPodの
作成、image pull、実推論、metrics/result取得を示さない。実providerを作成する
`live`は、上記identityをResolverの確定出力で埋め、費用上限とcleanupを確認して
から一度だけ行う。

PowerShellから直接WSLを起動するとlogin PATHにある`hf`が見えない場合がある。
ローカル検証はWSL login shellで実行する。これはprovider障害ではなく、CLI PATHの
ローカル実行条件である。

## ロールバックと次の安全な作業

wrapperは追加ファイルであり、既存のprovider実装や外部artifactを変更しない。
削除すれば従来のstatic／mock入口へ戻せる。次はResolverが発行したimage digest、
fixture revision、manifest SHAを`.env`へ手動転記せず、実験入力として明示的に渡し、
`--require-launch-inputs`をPASSさせる。その後、HFまたはRunPodのbatch=1のみを
guarded実行し、receipt、content probe、metrics URI／SHAを個別に確認する。
