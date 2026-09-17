"""Security checks exercise an isolated Git index, never the user's repository."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECK = Path(__file__).resolve().parents[2] / "scripts" / "check_publication.py"


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".env\n.env.*\n!.env.example\n")
    return tmp_path


def check(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK), *args],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )


def test_ignored_environment_is_excluded_and_example_is_publishable(repository: Path) -> None:
    (repository / ".env").write_text("LOCAL_PRIVATE_CONTENT")
    (repository / ".env.example").write_text("MISTRAL_API_KEY=\n")
    result = check(repository)
    assert result.returncode == 0
    assert "2 fichiers" in result.stdout
    assert "LOCAL_PRIVATE_CONTENT" not in result.stdout + result.stderr


def test_force_added_environment_is_blocked(repository: Path) -> None:
    (repository / ".env").write_text("LOCAL_PRIVATE_CONTENT")
    subprocess.run(["git", "add", "--force", ".env"], cwd=repository, check=True)
    result = check(repository, "--staged")
    assert result.returncode == 1
    assert ".env: fichier exclu" in result.stdout
    assert "LOCAL_PRIVATE_CONTENT" not in result.stdout + result.stderr


def test_staged_notebook_output_is_blocked_even_if_working_copy_is_clean(repository: Path) -> None:
    notebook = repository / "example.ipynb"
    content = {
        "cells": [
            {
                "cell_type": "code",
                "outputs": [{"text": "PRIVATE_NOTEBOOK_OUTPUT"}],
                "execution_count": 1,
            }
        ],
        "metadata": {},
    }
    notebook.write_text(json.dumps(content))
    subprocess.run(["git", "add", "example.ipynb"], cwd=repository, check=True)
    content["cells"][0].update(outputs=[], execution_count=None)
    notebook.write_text(json.dumps(content))
    assert check(repository).returncode == 0
    result = check(repository, "--staged")
    assert result.returncode == 1
    assert "example.ipynb: nettoyer" in result.stdout
    assert "PRIVATE_NOTEBOOK_OUTPUT" not in result.stdout + result.stderr


def test_untracked_notebook_outputs_are_checked_before_git_add(repository: Path) -> None:
    (repository / "example.ipynb").write_text(
        json.dumps({"cells": [{"outputs": [{"text": "PRIVATE_NOTEBOOK_OUTPUT"}]}]})
    )
    result = check(repository)
    assert result.returncode == 1
    assert "PRIVATE_NOTEBOOK_OUTPUT" not in result.stdout + result.stderr
