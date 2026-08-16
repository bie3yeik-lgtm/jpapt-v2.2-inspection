import torch
import nemo
import nemo.collections.asr as nemo_asr


MODEL_ID = "nvidia/parakeet-tdt_ctc-0.6b-ja"


def main() -> None:
    print(f"NeMo version: {nemo.__version__}")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"Loading model: {MODEL_ID}")

    model = nemo_asr.models.ASRModel.from_pretrained(
        model_name=MODEL_ID
    )

    print(f"Model class: {type(model).__name__}")
    print(f"Device: {model.device}")
    print("Model load: OK")


if __name__ == "__main__":
    main()
