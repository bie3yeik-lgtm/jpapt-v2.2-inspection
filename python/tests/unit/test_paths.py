from __future__ import annotations

from pathlib import Path

from parakeet_onnx.config.paths import find_repository_root


def test_find_repository_root_from_child(tmp_repo: Path) -> None:
    child = tmp_repo / "python" / "src" / "parakeet_onnx"
    assert find_repository_root(child) == tmp_repo.resolve()


def test_find_repository_root_with_environment_override(
    tmp_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "PARAKEET_ONNX_REPO_ROOT",
        str(tmp_repo),
    )

    assert find_repository_root() == tmp_repo.resolve()
