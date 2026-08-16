# HF Routing Snapshots

## 現在routing

Target identityとstorage routingは分離します。

`config/hf-targets/*.toml` はmodel/upstream/reference framework/profile set等のtarget定義を持ち、workflow実行時のHF routingは `HF_TARGETS_JSON` から解決します。

## Snapshot principle

```text
現在のrouting          HF_TARGETS_JSON
Target semantics       config/hf-targets/*.toml
実行時routing          run-context.json metadata
model provenance       revision bundle / reference.json
runtime semantics      runtime.json + ASR catalog fingerprint
```

Repository Variableは将来変更できます。そのため過去runのBucket/model routingを現在値から逆算しません。

## Target change

同じ論理targetを別Bucketへ移す場合でもruntime profileやmodel identityを書き換える必要はありません。routing変更は新しいexecution snapshotへ記録します。

## Reproducibility

再現時はrun-contextに固定されたcandidate/revision/config/runtime/routing情報を優先します。「現在のtarget mappingが同じはず」という仮定を置きません。
