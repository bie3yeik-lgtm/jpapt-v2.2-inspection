# Work history: parquet-evaluation-capsules

## 作業依頼内容

以下の2資料を実装要件として読み解き、Parquet Dataset入力、Hugging Face Bucket内でのParquet運用、Rust/ONNX評価境界の既知障害を実態調査し、条件に適合する評価Datasetsを選定した上で実装を進める。

- `inspection/advices/Case-Parquet-buckets.md`
- `inspection/advices/jpapt-experiment-capsule-v1-rust-parquet-design.md`

破壊的変更は許可されている。既存の未安定schema/APIとの互換性より、Rust typed contractとParquet analytical resultの単一正本を優先する。

## 作業概要

- branch: `agent/parquet-evaluation-capsules`
- 対象repo: `bie3yeik-lgtm/jpapt-v2.2-inspection`
- 主要対象: Rust workspace / `asr-eval` / evaluation dataset contracts / HF Bucket run+benchmark layout / GitHub Actions
- 調査済み候補dataset: `japanese-asr/ja_asr.jsut_basic5000`。HF上で Audio+Text、Parquet、5,000 rows、test splitとして公開されていることを確認。
- 実装方針: Arrow/Parquetを`asr-runtime`へ依存させず、persistence専用Rust crateを分離する。ONNX tensor境界ではArrow bufferのzero-copyをcanonicalにせず、materialized audio fileおよびowned contiguous inputを維持する。

## 作業判断

1. ParquetはONNX tensor formatではなく、dataset/evaluation persistence formatとして扱う。
2. Dataset ParquetのAudio列を直接ORT tensorへ流さない。既存の`ResolvedDatasetSample.audio_path` materialization contractを維持し、Parquet→materialized audio→canonical waveform→ORTとする。
3. HF Bucketではcandidate artifact自体をParquet化せず、run/benchmark/sample analytical recordsをimmutable capsuleとしてParquet化する。
4. ASR metricsはParquetではFloat64、ONNX inputはFloat32を維持する。
5. 必須推論列のnull、NaN/Infinity、unsafe nested/large binary依存をrejectする。失敗値はstatus/error列で表現する。
6. Arrow/Parquet schemaはflatかつversionedとし、Rust domain modelを正本にしてJSON/Parquet serializerを分岐させる。
7. Arrow→ONNX zero-copyは既知のoffset/contiguity/null semantics問題があるため初期実装では採用しない。
8. 破壊的変更が許可されたため、未安定なJSONL中心contractは必要に応じてtyped domain/Parquet中心へ再設計する。

## 作業過程

1. 2本のadviceを確認。主障害はParquetとONNXの直接衝突ではなく、Arrow RecordBatch→tensor境界、null/variable-length、row group memory、schema evolution、HF Bucket shard/parallelism境界に集中していることを確認。
2. arrow-rs/parquet現行docsを確認。`ParquetRecordBatchReader`はRecordBatch iterator、`ArrowWriter`はrow group全体をbufferし、memory thresholdで`flush`可能。row groupを小さくし過ぎるとmetadata/compression面のtrade-offがある。
3. HF上の`japanese-asr/ja_asr.jsut_basic5000`を確認。Audio/Text、Parquet format、test 5,000 rows、約2.25GBで、初期の日本語ASR評価datasetとして適合性が高い。
4. 現行Rust `ResolvedManifest`は全sampleのmaterialized `audio_path`を要求しており、この契約はParquet Dataset導入後もONNX入力安全境界として維持する。
5. 現行`asr-eval`はper-sample結果を`serde_json::Value`へ直接構築している。これをtyped domainへ引き上げ、Parquet persistence crateと接続する実装へ進む。

### 現在の状態

- 完了: advice理解、初期障害分類、JSUT Basic5000適合確認、Rust既存境界確認、実装branch作成
- 未完了: `asr-capsule` crate、Parquet schema/writer/reader/verify、`asr-eval`接続、dataset Parquet locator contract、workflow、tests、CI
- 次の具体的操作: workspaceにexact-pinned Arrow/Parquet依存と`asr-capsule` crateを追加し、flat/versioned ExperimentCapsule schemaとround-trip/integrity testsを実装する。
