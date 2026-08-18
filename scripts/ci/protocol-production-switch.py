#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement target, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


v2 = ".github/workflows/candidate-package-evaluate-v2.yml"
replace_once(
    v2,
    """    steps:
      - uses: actions/checkout@v7
      - name: Build completion receipt and dispatch body
""",
    """    steps:
      - uses: actions/checkout@v7
      - uses: dtolnay/rust-toolchain@stable
      - name: Build completion receipt and dispatch body
""",
)
replace_once(
    v2,
    """        run: >-
          python scripts/ci/build-candidate-completion-receipt.py
          --receipt .ci/candidate-completion-receipt.json
          --dispatch-body .ci/candidate-completion-dispatch.json
""",
    """        run: >-
          cargo run --quiet --locked -p asr-contracts --bin asr-candidate-protocol-build --
          receipt
          --receipt .ci/candidate-completion-receipt.json
          --dispatch-body .ci/candidate-completion-dispatch.json
""",
)

gateway = ".github/workflows/candidate-request-gateway.yml"
replace_once(
    gateway,
    """  reject:
    name: Emit candidate request rejection
    needs: plan
    if: ${{ always() && needs.plan.result == 'failure' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Build rejection evidence
""",
    """  reject:
    name: Emit candidate request rejection
    needs: plan
    if: ${{ always() && needs.plan.result == 'failure' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: dtolnay/rust-toolchain@stable
      - name: Build rejection evidence
""",
)
start = """          python scripts/ci/build-candidate-request-rejection.py \\
            --rejection .ci/rejection/candidate-request-rejection.json \\
            --dispatch-body .ci/rejection/candidate-request-rejection-dispatch.json
"""
end_marker = """          request_key="$(python scripts/ci/build-candidate-request-lifecycle.py --request-key "$request_id")"
"""
p = Path(gateway)
text = p.read_text(encoding="utf-8")
start_index = text.find(start)
if start_index < 0:
    raise SystemExit("gateway: rejection builder block start not found")
end_index = text.find(end_marker, start_index)
if end_index < 0:
    raise SystemExit("gateway: rejection extraction block end not found")
replacement = """          cargo run --quiet --locked -p asr-contracts --bin asr-candidate-protocol-build -- \\
            rejection \\
            --rejection .ci/rejection/candidate-request-rejection.json \\
            --dispatch-body .ci/rejection/candidate-request-rejection-dispatch.json
          request_id="$(jq -er '.request_id' .ci/rejection/candidate-request-rejection.json)"
          receipt_repository="$(jq -er '.receipt_repository' .ci/rejection/candidate-request-rejection.json)"
"""
text = text[:start_index] + replacement + text[end_index:]
p.write_text(text, encoding="utf-8")
