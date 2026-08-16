# Hugging Face Bucket Operations

## Script surface

HF操作は `scripts/hf/` を正本とします。主要entrypoint:

```text
hf-allocate-id.sh
hf-request-id.sh
hf-fetch-candidate.sh
hf-fetch-reference.sh
hf-fetch-revisions.sh
hf-push-candidate.sh
hf-push-config-version.sh
hf-push-run.sh
hf-push-benchmark.sh
hf-promote-candidate.sh
hf-promote-model.sh
hf-update-root-readme.sh
```

## Candidate publish

```text
local candidate
  ↓ strict CandidateArtifacts validation
Central Allocator
  ↓ candidate-id
candidates/<candidate-id>/ upload
```

allocatorはcandidate IDをmetadataへ追記しません。取得時は `.candidate-id` をlocal candidate rootへmaterializeし、runtime側がそこからidentityを解決します。

## Config publish

human-authored/reference inputsをversion directoryへ固定し、`runtime.json` を含むcanonical 4-file bundleとしてpushします。`runtime.json` がないrevision bundleはサポートしません。

## Run / benchmark

run artifactは `runs/<run-id>/`、比較可能なbenchmark receiptは `benchmarks/<candidate-id>/<environment-provider>/` に保存します。

## Promotion

promotionは開発Bucketのcandidate/run evidenceを基に実施します。Model Repoをmutable experiment historyの置場にせず、promoted artifactを配布対象として扱います。

## 安全規則

-既存immutable ID/versionを上書きしない。
- candidate metadataへgenerated factsを逆流させない。
- 現在routingを過去run provenanceの代用品にしない。
- upload前にstrict candidate/runtime contract validationを通す。
