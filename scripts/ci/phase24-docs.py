from pathlib import Path
import re

replacements = {
    "docs/README.md": [
        (
            "- ID prefixのsource of truthは `config/hf-allocation-catalog.json`。",
            "- allocation prefixはcollectionから決定します（`candidates -> candidate`, `experiments -> experiment`, `config -> config`）。prefix用JSONは持ちません。",
        ),
    ],
    "docs/architecture.md": [
        (
            "- `config/hf-allocation-catalog.json`\n",
            "- HF allocation namingはcollectionから導出し、prefix catalogは保持しません。\n",
        ),
    ],
    "docs/contracts.md": [
        (
            "| source-controlled | `config/asr-catalog.json`, `config/hf-allocation-catalog.json` | repository変更としてのみ |",
            "| source-controlled | `config/asr-catalog.json`, `config/hf-targets/*.toml` | repository変更としてのみ |",
        ),
    ],
    "docs/hf-buckets.md": [
        (
            "candidate IDは `config/hf-allocation-catalog.json` に従って中央Allocatorが採番します。",
            "candidate IDは中央Allocatorがcanonical/historical layout双方の最大6桁suffixを見て `candidate-NNNNNN` を自動採番します。prefix設定JSONは不要です。candidate IDを省略したreadではcanonical `candidates/candidate-NNNNNN` の最新値を優先し、canonicalが存在しない既存Bucketに限って `<variant>/candidate-NNNNNN` をread-only fallbackとして解決します。",
        ),
    ],
    "docs/workflows.md": [
        ("config/hf-allocation-catalog.json\n", ""),
        (
            "prefixは `config/hf-allocation-catalog.json` のkeyからのみ解決します。",
            "prefixはcollectionからRustが決定します。workflowはprefix keyを入力せず、candidate IDも省略時は対象Bucketから自動解決します。",
        ),
    ],
}

for filename, pairs in replacements.items():
    path = Path(filename)
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in text:
            raise SystemExit(f"missing expected text in {filename}: {old!r}")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")

path = Path("docs/json-reference.md")
text = path.read_text(encoding="utf-8")
pattern = re.compile(r"## 2\. `config/hf-allocation-catalog\.json`.*?(?=\n## 3\.)", re.S)
replacement = """## 2. HF allocation policy（JSON入力なし）

HF allocationのprefixは設定JSONではなくcollectionからRustで決定します。

| collection | canonical prefix | canonical path |
|---|---|---|
| `candidates` | `candidate` | `candidates/candidate-NNNNNN/` |
| `experiments` | `experiment` | `experiments/experiment-NNNNNN/` |
| `config` | `config` | `config/versions/config-NNNNNN/` |

連番はcanonicalとhistorical layout双方に存在するallocation IDの6桁suffix最大値 + 1です。過去の異なるprefixや`<variant>/candidate-NNNNNN`、`<variant>/exp-NNNNNN`もID再利用防止のためsequence計算に含めますが、新規writeはcanonical prefix/layoutのみです。

candidate readはcanonical pathを優先します。canonical candidateが存在しないhistorical Bucketに限り、runtime variantを使って `candidates/<variant>/candidate-NNNNNN/` をread-only fallbackとして解決します。exact candidate IDを指定した場合も同じresolverを通るため、workflow間ではcandidate IDだけを受け渡せます。

このpolicyには人間が編集すべきJSON定義はありません。
"""
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit("allocation catalog section was not found exactly once")
text = text.replace("config/hf-allocation-catalog.json\n", "")

target_note = """
### HF target定義の最小入力

`config/hf-targets/<target-id>.toml` はroutingに必要な値だけを保持します。target IDはファイル名から、upstream repo / framework / model identityは `config/models/<target-id>.toml` から導出します。

```toml
schema_version = 3

[runtime]
profile_set = "parakeet-tdt-ctc-v1"

[storage]
bucket = "gawohok7/jpapt-v2.2-dev-bucket"
model_repo = "gawohok7/jpapt-v2.2-dev"
```

同じidentityを複数ファイルへ再入力しないことがcontractです。workflowは `hf_target` のみを選択し、Bucket / model repo / upstream repo / framework / runtime profile / decoderを自動補完します。candidate IDは省略可能で、対象Bucketから自動解決されます。
"""
marker = "\n## 3."
pos = text.find(marker)
if pos < 0:
    raise SystemExit("json-reference section 3 not found")
text = text[:pos] + target_note + text[pos:]
path.write_text(text, encoding="utf-8")
