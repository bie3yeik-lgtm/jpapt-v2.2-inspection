# GitHub Actions version固定ポリシー

## 目的

本リポジトリでは、過去にworkflow修正時にAction versionが古い値へ巻き戻る問題が発生したため、主要な公式Actionのversionを**開発規約かつCI contract**として固定します。

以下が正しい値です。

```yaml
- uses: actions/checkout@v7
- uses: actions/setup-python@v7
- uses: actions/upload-artifact@v7
- uses: actions/cache@6
```

これらを`@v4`、`@v5`等へ戻してはいけません。

## 適用範囲

`.github/workflows/*.yml`に存在する以下のActionすべてが対象です。

| Action | 必須version |
|---|---|
| `actions/checkout` | `v7` |
| `actions/setup-python` | `v7` |
| `actions/upload-artifact` | `v7` |
| `actions/cache` | `6` |

その他のAction（例: `dtolnay/rust-toolchain`, `actions/download-artifact`）は、この文書のversion固定対象とは別に管理します。

## CIによる強制

人間向け文書だけでは巻き戻りを防げないため、次のscriptをsource-controlled contractとして実行します。

```text
scripts/ci/validate-github-action-versions.py
```

`Validate HF Layout`のPR/push jobで全workflowを走査し、対象Actionが指定version以外なら失敗します。

例:

```text
actions/checkout@v4
```

が追加されると、CIは次の種類のエラーとして拒否します。

```text
ERROR: .github/workflows/example.yml:<line>:
actions/checkout@v4 is forbidden; required=actions/checkout@v7
```

## 開発時のルール

workflowを新規作成・編集する場合は、既存workflowをコピーした後でもAction versionを必ずこの文書と照合してください。

AI/Coding Agentへworkflow変更を依頼する場合も、次を不変条件として扱います。

```text
DO NOT downgrade or rewrite:
  actions/checkout@v7
  actions/setup-python@v7
  actions/upload-artifact@v7
  actions/cache@6
```

Actionを追加・削除した結果、この固定ポリシー自体を変更する必要が生じた場合は、workflowだけを先に変更せず、次を同一PRで更新します。

```text
docs/github-actions-version-policy.md
scripts/ci/validate-github-action-versions.py
該当workflow
```

## なぜdocsとCIの両方を持つか

```text
docs
  = 人間・AIに意図を伝える

CI guard
  = 意図に反する変更をmerge前に機械的に止める
```

どちらか一方だけに依存しません。
