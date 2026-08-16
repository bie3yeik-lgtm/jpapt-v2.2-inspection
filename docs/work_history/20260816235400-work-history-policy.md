# Work history: work-history-policy

## 作業依頼内容

`docs/work_history/` を新設し、今後の作業記録を `yyyymmddhhMMss-{workSurveyName}.md` の命名規則で保存する運用を `AGENTS.md` に定義する。

記録の主目的は次の2点である。

1. 別の作業者・別セッション・別エージェントが、過去の会話を完全に再読しなくても途中から安全に作業を再開できること。
2. 何を依頼され、何を判断し、どのような過程を経て結果に至ったかを後からauditできること。

最低限、各記録には次の4区分を含める。

- 作業依頼内容
- 作業概要
- 作業判断
- 作業過程

## 作業概要

- `docs/work_history/` の最初の記録として本ファイルを追加した。
- `AGENTS.md` にwork historyの恒久運用ルールを追記した。
- 記録は作業完了後に一括生成するだけではなく、長時間・多段階作業では重要な判断や状態変化ごとに更新する方針とした。
- work historyは実装コードやschemaの正本ではなく、再開・監査のための時系列説明資料として扱う。
- 現在のbranchは `agent/nemo-onnx-asr-quality`、関連PRはdraft PR #29である。

## 作業判断

### 1. ファイル名

形式は次で固定する。

```text
docs/work_history/yyyymmddhhMMss-{workSurveyName}.md
```

- timestampは作業記録を開始した時刻を基準とする。
- `workSurveyName` は作業内容が識別できる短いkebab-case名とする。
- 同一作業を継続する間は同じファイルを更新し、細かな各commitごとに別ファイルを増殖させない。
- 明確に別の依頼・別の調査単位へ移行した場合は新しいwork historyを開始する。

### 2. 必須内容

4つの必須区分を単なる完了報告にせず、次の観点を残す。

- **作業依頼内容**: 元の依頼、制約、対象repo/model/bucket/provider等。
- **作業概要**: 実施範囲、変更対象、現在の到達点。
- **作業判断**: 採用案・不採用案・根拠・安全上の判断・推測を避けた箇所。
- **作業過程**: 実施順序、重要commit/PR/workflow/run、検出した障害、修正、検証結果、残件。

### 3. 再開可能性

作業途中で終了しても、記録から少なくとも次が分かる状態を目標とする。

```text
現在のbranch / PR
最新の重要commit
完了済み項目
未完了項目
直前に確認したCI / HF状態
次に行うべき具体的操作
既知の障害・禁止事項
```

値が存在しない場合に架空の値を埋めない。未確定・未検証・取得不能はそのまま明記する。

### 4. audit性

work historyでは結果だけでなく、重要な判断理由と失敗経路も残す。

特に次は省略しない。

- destructive redesignを選んだ理由
- schema/contractを変更した理由
- provider executionを証明できなかったケース
- HF/GitHub等の外部サービス境界で発生したエラー
- real-model evidenceとsynthetic/unit evidenceの区別
- 一時workflowや一時artifactを作成・削除した事実
- quality threshold等を推測せず明示入力にした判断

秘密情報、token、credential、不要な個人情報は記録しない。

### 5. work history自体の扱い

`docs/work_history/` はappend-orientedなhistorical evidenceとして扱う。過去の判断や失敗を隠すために既存記録を破壊的に書き換えない。訂正が必要な場合は、何を訂正したかと理由が追跡できる形で修正する。

またwork historyはruntime truthではない。実装・schema・generated contract・source-controlled config・`AGENTS.md`がそれぞれの正本であり、work historyはhandoff/auditを支援する記録である。

## 作業過程

1. 現行 `AGENTS.md` を確認し、同ファイルがrepository constitutionかつ唯一の破壊的変更禁止ファイルとして既に定義されていることを確認した。
2. work historyルールはこのconstitutionへ追加するべき恒久運用ルールと判断した。
3. `docs/work_history/` はGitが空directoryを保持できないため、本作業自体の記録である `20260816235400-work-history-policy.md` を最初のentryとして作成した。作成commitは `f3651df6320b1f9b7e5d068e56ff47f2ba63e5d8`。
4. `AGENTS.md` へ、命名規則、4必須区分、逐次更新、handoff/audit目的、未検証事項を正直に残す規則、audit recordの非破壊性を追記した。
5. constitution追記のため一時workflow `_append-work-history-rule.yml` を使用した。run `31954175168` はSUCCESSし、bot commit `1fa5156ab9e24d4ab78ae811316ea0f67cb37075` で `AGENTS.md` が更新された。
6. 追記後の確認で `negative efidence` という綴り誤りを検出した。意味上のルール変更は行わず、1語のみ `negative evidence` へ訂正した。
7. 訂正用一時workflow `_fix-work-history-policy-typo.yml` のrun `31954230379` はSUCCESSした。
8. 2つの一時workflowは恒久APIにしないというrepository ruleに従って双方とも削除した。最後の削除commitは `b4f188bd76c11e5e33df8de50ad2706e40b0ee9e`。
9. `AGENTS.md` 上で `## Work history and audit trail` 節が存在し、`docs/work_history/`、命名規則、必須4区分、resumability/auditability、逐次更新、未検証値を推測しないこと、secretを記録しないこと、append-oriented audit evidenceであることを確認した。
10. 本ファイルを現在の状態へ更新した。次に最新headの通常CIを確認する。PR #29は明示指示がないためdraftのまま維持する。
