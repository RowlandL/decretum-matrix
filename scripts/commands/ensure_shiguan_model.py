"""Ensure the pinned Laya recall model is present as real files in the install state.

Install-time asset provisioning for the `shiguan-recall` capability.

The model is **not redistributed** by this repository: this command fetches exactly
the pinned upstream revision and verifies every file by size and SHA-256 before it
is used. Files are written as real files (not links) so later skill invocations
resolve them from the install state.

Usage:
  python -B scripts/ensure_shiguan_model.py             # read-only plan
  python -B scripts/ensure_shiguan_model.py --apply     # download, verify, write
  python -B scripts/ensure_shiguan_model.py --apply --json
"""

from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path

_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request

sys.dont_write_bytecode = True

SKILL_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_RELATIVE = Path("training/laya-shiguan/schema/model-manifest.json")
TARGET_RELATIVE = Path("training/laya-shiguan/models/laya-multilingual")
RECEIPT_RELATIVE = Path("training/laya-shiguan/models/model-bootstrap-receipt.json")
RESOLVE_TEMPLATE = "https://huggingface.co/{model}/resolve/{revision}/{path}"
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    """Install-time artifact digest (the only permitted hashing use here)."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(root: Path) -> dict:
    path = root / MANIFEST_RELATIVE
    if not path.is_file():
        raise SystemExit(f"model manifest missing: {MANIFEST_RELATIVE}")
    return json.loads(path.read_text(encoding="utf-8"))


def inspect(root: Path, manifest: dict) -> list[dict]:
    target = root / TARGET_RELATIVE
    rows = []
    for entry in manifest["files"]:
        path = target / entry["path"]
        state = "MISSING"
        if path.is_file():
            if path.stat().st_size != entry["size"]:
                state = "SIZE_MISMATCH"
            elif sha256_of(path) != entry["sha256"]:
                state = "DIGEST_MISMATCH"
            else:
                state = "OK"
        rows.append({**entry, "state": state, "local": str(path)})
    return rows


def download(url: str, destination: Path, expected: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=str(destination.parent), prefix=destination.name + ".", suffix=".part", delete=False
    )
    temp = Path(handle.name)
    try:
        with handle:
            with urllib.request.urlopen(url, timeout=120) as response:
                shutil.copyfileobj(response, handle, CHUNK)
        actual_size = temp.stat().st_size
        if actual_size != expected["size"]:
            raise ValueError(f"size mismatch: expected {expected['size']}, got {actual_size}")
        actual_sha = sha256_of(temp)
        if actual_sha != expected["sha256"]:
            raise ValueError("sha256 mismatch")
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ensure-shiguan-model",
        description="Provision the pinned Laya recall model into the install state (real files, verified).",
    )
    parser.add_argument("--apply", action="store_true", help="Download and write; default is a read-only plan.")
    parser.add_argument("--root", default=None, help="Skill root to provision; defaults to this script's skill root.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else SKILL_ROOT
    manifest = load_manifest(root)
    model = manifest["model"]
    revision = manifest["revision"]
    model_dir = root / TARGET_RELATIVE

    rows = inspect(root, manifest)
    pending = [row for row in rows if row["state"] != "OK"]

    if args.apply:
        failures = []
        for row in pending:
            url = RESOLVE_TEMPLATE.format(model=model, revision=revision, path=row["path"])
            try:
                download(url, Path(row["local"]), row)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                failures.append({"path": row["path"], "problem": str(exc)[:200]})
        rows = inspect(root, manifest)
        receipt = {
            "schema": "court.shiguan_model_bootstrap_receipt.v1",
            "model": model,
            "revision": revision,
            "license": manifest.get("license"),
            "backbone": manifest.get("backbone"),
            "root": str(root),
            "target": str(model_dir),
            "redistributed_by_repository": False,
            "verified_files": [{"path": r["path"], "size": r["size"], "sha256": r["sha256"]} for r in rows],
            "failures": failures,
            "ok": not failures and all(r["state"] == "OK" for r in rows),
        }
        receipt_path = root / RECEIPT_RELATIVE
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ready = all(row["state"] == "OK" for row in rows)
    payload = {
        "ok": ready,
        "apply": args.apply,
        "model": model,
        "revision": revision,
        "root": str(root),
        "target": str(model_dir),
        "files": [{"path": r["path"], "state": r["state"], "size": r["size"]} for r in rows],
        "pending": [r["path"] for r in pending],
        "note": "real files, verified by size + sha256; model is not redistributed by this repository",
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"model      : {model} @ {revision}")
        print(f"target     : {model_dir}")
        for row in rows:
            print(f"  {row['state']:<15} {row['path']}")
        print("ready" if ready else f"pending {len(pending)} file(s); rerun with --apply")
    return 0 if (ready or not args.apply) else 1


if __name__ == "__main__":
    raise SystemExit(main())
