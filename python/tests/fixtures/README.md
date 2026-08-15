# Test Fixtures

This directory is reserved for small, deterministic test fixtures.

Do not commit large ASR assets here.

Allowed examples:

- tiny JSON documents
- tiny JSONL manifests
- small metadata files
- very short synthetic WAV files if a test cannot generate them dynamically

Do not store:

```text
*.onnx
*.nemo
large *.wav
*.flac
*.npy
*.npz
dataset snapshots
model weights
```

Most audio tests should generate synthetic waveforms at runtime using NumPy and
write them to pytest temporary directories.
