# 1
docker run --rm --gpus all \
  nvidia/cuda:12.9.1-base-ubuntu24.04 \
  nvidia-smi

# 2
./scripts/docker/nemo-build.sh

# 3
./scripts/docker/nemo-shell.sh

# コンテナ内
# 4
python -c "import nemo.collections.asr; print('NeMo ASR OK')"

# ホストから
# 5
docker run --rm --gpus all \
  --shm-size=8g \
  -e HF_TOKEN \
  -v "$PWD:/workspace" \
  parakeet-nemo:dev \
  python scripts/reference/check_parakeet.py
