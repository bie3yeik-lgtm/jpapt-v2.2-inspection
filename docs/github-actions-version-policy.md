# GitHub Actions version固定ポリシー

## 目的

本リポジトリでは、workflow修正時にAction versionが意図せず変更されることを防ぐため、主要な公式Actionのversionを**開発規約かつCI contract**として固定します。

以下が正しい値です。

```yaml
- uses: actions/checkout@v6
- uses: actions/setup-python@v7
- uses: actions/upload-artifact@v7
- uses: actions/cache@v6
- uses: actions/cache/restore@v6
- uses: actions/cache/save@v6
```

`actions/cache/restore` と `actions/cache/save` は必須利用ではありませんが、使用する場合は必ず `@v6` とします。

## 適用範囲

`.github/workflows/*.yml`に存在する以下のActionが対象です。

| Action | 固定version | 利用必須 |
|---|---:|---:|
| `actions/checkout` | `v6` | yes |
| `actions/setup-python` | `v7` | yes |
| `actions/upload-artifact` | `v7` | yes |
| `actions/cache` | `v6` | yes |
| `actions/cache/restore` | `v6` | no |
| `actions/cache/save` | `v6` | no |

その他のAction（例: `dtolnay/rust-toolchain`, `actions/download-artifact`）は、この固定ポリシーとは別に管理します。

## CIによる強制

次のscriptをsource-controlled contractとして実行します。

```text
scripts/ci/validate-github-action-versions.py
```

`Validate HF Layout`のPR/push jobで全workflowを走査し、対象Actionが指定version以外なら失敗します。

例えば、

```text
actions/checkout@v7
```

が追加されると、CIは次の種類のエラーとして拒否します。

```text
ERROR: .github/workflows/example.yml:<line>:
actions/checkout@v7 is forbidden; required=actions/checkout@v6
```

同様に、

```text
actions/cache@6
actions/cache@v5
actions/cache/restore@v5
actions/cache/save@v5
```

も拒否されます。

## 開発時の不変条件

```text
DO NOT downgrade, upgrade, or rewrite:
  actions/checkout@v6
  actions/setup-python@v7
  actions/upload-artifact@v7
  actions/cache@v6
  actions/cache/restore@v6   # when used
  actions/cache/save@v6      # when used
```

Action version policyそのものを変更する必要がある場合は、workflowだけを先に変更せず、次を同一PRで更新します。

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
