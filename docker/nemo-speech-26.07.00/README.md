---
license: agpl-3.0
title: Parakeet NeMo Environment
sdk: docker
---

```sh
python evaluate.py --profile smoke
```

## この段階ではまだ入れないもの

Dockerfile.nemo に以下はまだ入れない方がよいです。

```
Rust
Cargo
sccache


onnxruntime-gpu
TensorRT


CoreML
DirectML


Kotoba v2.2 pipeline dependencies


Diarization
Punctuation
```

Dockerfile.nemo の責務を「NVIDIAのParakeet referenceを再現し、後でONNX exportすること」に限定するためです。

Rustは別の、

`docker/Dockerfile.rust`

へ分けます。
