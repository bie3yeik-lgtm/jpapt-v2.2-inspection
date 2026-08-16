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

- `docs/work_history/` の最初の記録として本ファイルを追加する。
- `AGENTS.md` にwork historyの恒久運用ルールを追記する。
- 記録は作業完了後に一括生成するだけではなく、長時間・多段階作業では重要な判断や状態変化ごとに更新する。
- work historyは実装コードやschemaの正本ではなく、再開・監査のための時系列説明資料として扱う。

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

## 作業過程

1. 現行 `AGENTS.md` を確認し、同ファイルがrepository constitutionかつ唯一の破壊的変更禁止ファイルとして既に定義されていることを確認した。
2. work historyルールはこのconstitutionへ追加するべき恒久運用ルールと判断した。
3. `docs/work_history/` はGitが空directoryを保持できないため、本作業自体の記録である本ファイルを最初のentryとして作成した。
4. 次に `AGENTS.md` へ命名規則、4必須区分、逐次更新、handoff/audit目的、未検証事項を正直に残す規則を追記する。
5. 追記完了後は通常CIを確認し、PRは明示指示がない限りdraftのまま維持する。
