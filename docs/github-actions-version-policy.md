# GitHub Actions Version Policy

workflowのAction referenceは、repositoryで実際に採用されているversionを基準に更新します。

## ルール

- 既存workflowを編集する際、理由なくAction major versionを巻き戻さない。
- `actions/checkout`, `actions/setup-python`, `actions/cache` 等は各workflow間で同じ世代へ揃える。
- syntaxは `@vN` を基本とし、誤って `@N` を導入しない。
- dependency updateだけのためにevaluation semanticsやHF contractを変更しない。
- Action major upgrade時は対象workflowのCIを実行して確認する。

## 現行例

repositoryでは `actions/checkout@v7`, `actions/setup-python@v7`, `actions/cache@v6` を使用するworkflowがあります。文書内の固定例より `.github/workflows/*.yml` を正本とします。

## Security

外部Actionを追加する場合はpublisher、権限、token exposure、fork PR時の挙動を確認します。workflow `permissions` は必要最小限を維持し、read-only jobへwrite permissionを付けません。

この文書はversion catalogではありません。実versionを知るときはworkflow sourceを確認してください。
