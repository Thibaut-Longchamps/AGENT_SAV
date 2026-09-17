"""Check publishable files without printing their contents or changing the Git index.

By default, inspect tracked files plus untracked, non-ignored files. --staged
reads the entire index, including partially staged notebooks. --tracked is for CI.
An optional Gitleaks executable scans a temporary snapshot of the same files.
"""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def git(*args: str, input_data: bytes | None = None) -> bytes:
    return subprocess.check_output(["git", *args], input=input_data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--staged", action="store_true")
    modes.add_argument("--tracked", action="store_true")
    parser.add_argument("--gitleaks", metavar="EXECUTABLE")
    args = parser.parse_args()
    os.chdir(os.fsdecode(git("rev-parse", "--show-toplevel")).strip())

    options = ["--cached"]
    if not (args.staged or args.tracked):
        options += ["--others", "--exclude-standard"]
    paths = sorted(set(git("ls-files", "-z", *options).split(b"\0")) - {b""})
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        input=b"\0".join(paths) + (b"\0" if paths else b""),
        capture_output=True,
        check=False,
    )
    if ignored.returncode not in (0, 1):
        raise RuntimeError("Unable to verify ignore rules")
    forbidden = set(ignored.stdout.split(b"\0")) - {b""}
    errors = []
    count = 0
    with tempfile.TemporaryDirectory(prefix="orderops-publication-") as temporary:
        for raw_path in paths:
            name = os.fsdecode(raw_path)
            path = Path(name)
            if raw_path in forbidden:
                errors.append(f"{name}: fichier exclu mais présent dans Git")
                continue
            if path.is_symlink():
                errors.append(f"{name}: lien symbolique à examiner avant publication")
                continue
            if args.staged:
                content = git("show", f":{name}")
            elif path.is_file():
                content = path.read_bytes()
            else:
                continue
            count += 1
            if path.suffix == ".ipynb":
                try:
                    notebook = json.loads(content)
                    dirty = bool(notebook.get("metadata", {}).get("widgets")) or any(
                        cell.get("outputs")
                        or cell.get("execution_count") is not None
                        or cell.get("attachments")
                        or any(k in cell.get("metadata", {}) for k in ("execution", "ExecuteTime"))
                        for cell in notebook["cells"]
                    )
                    if dirty:
                        errors.append(f"{name}: nettoyer sorties, pièces jointes et métadonnées")
                except (ValueError, KeyError, TypeError, AttributeError):
                    errors.append(f"{name}: notebook invalide")
            if args.gitleaks:
                target = Path(temporary) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)

        for error in errors:
            print(error)
        if errors:
            return 1
        if args.gitleaks:
            result = subprocess.run(
                [args.gitleaks, "dir", temporary, "--redact", "--no-banner"], check=False
            )
            if result.returncode:
                return result.returncode
    print(f"Publication : {count} fichiers vérifiés, hygiène OK.")
    if not args.gitleaks:
        print("Le scan des secrets est réalisé séparément par le hook Gitleaks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
