"""Temporary compatibility notes for resolver.py.

Apply these requirements to the repository's existing DatasetResolver:

1. Import DatasetMaterializer:
       from .materializer import DatasetMaterializer

2. In _resolve_entry(), after selecting each DatasetRecord:
       materialized = self.materializer.materialize(
           record=record,
           dataset_revision=lock.revision,
       )

3. Store:
       audio_path=materialized.audio_path
       audio_sha256=materialized.sha256

The repository version already contains this logic but currently has malformed
indentation around the materializer call. Fix that indentation before running
the resolver.

Duration filtering itself is fixed by the replacement models.py included in
this bundle, which uses half-open intervals [min, max).
"""
