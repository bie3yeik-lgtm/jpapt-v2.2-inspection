# RTF Resolver生成物配布の修正

## 発見した問題

merge後のRTF Resolverは、GHCR digest `sha256:67fae6c12ef6abb406b200984f81186da5a622a75b13ec476175193616d0b70c`
を入力としてfixtureを再生成した。しかし、receipt/manifest生成後のPR作成stepで
`git reset --hard origin/main`と`git clean -fd`を実行していたため、生成物が消失し、
「差分なし」と誤判定してdelivery PRを作成しなかった。

この結果、mainのreceiptは旧image digestを保持したままとなり、RTF Benchmark Runの
image identity gateを通過できない状態だった。

## 修正

PR作成stepでbranchを更新する前に、`rtf-scores/benchmark`の生成差分を
`$RUNNER_TEMP`へGit binary patchとして退避する。`origin/main`からbranchを作成した後、
patchを復元してからadd/commit/pushする。

これにより、最新のimage digest、manifest SHA-256、fixture revision、receiptがdelivery PRへ
確実に引き継がれる。patchはrunnerの一時領域に置き、repositoryへ残さない。

## 検証方針

- YAML内のshell構文と既存RTF workflow契約を検証する。
- merge後のRTF Resolverを新しいGHCR digestで再実行する。
- Resolver delivery PRのreceipt imageが新digestと一致することを確認する。
- そのPRをmainへ反映した後、RunPod smokeはbatch-1のみ実行する。

## 未検証事項

- この修正を反映したResolver workflowの実際のdelivery PR作成は未実施。
- RunPodのCUDA互換性ゲートが実ホスト割り当てで機能することは、delivery PR反映後に検証する。
