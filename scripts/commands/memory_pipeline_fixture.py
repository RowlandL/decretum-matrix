"""Synthetic native-memory pipeline fixture for Decretum Matrix.

The fixture proves the shape of scan -> adjudicate -> apply -> verify ->
reconcile without touching a real Codex, Hermes, or Claude memory store.
"""



from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from uuid import uuid4

sys.dont_write_bytecode = True


SCHEMA = "decretum.memory_pipeline_fixture.v1"
PIPELINE = ("scan", "adjudicate", "apply", "verify", "reconcile")
CANDIDATE_CONTENT = (
    "Decretum memory writeback must prove scan, adjudicate, apply, verify, "
    "and reconcile before a production capability claim is promoted."
)
SECRET_RE = re.compile(
    r"(?i)("
    r"api[_ -]?key\s*[:=]\s*[^\s;]+|"
    r"secret\s*[:=]\s*[^\s;]+|"
    r"password\s*[:=]\s*[^\s;]+|"
    r"authorization\s*[:=]\s*[^\s;]+|"
    r"bearer\s+[a-z0-9._~+/=-]{16,}|"
    r"token\s*[:=]\s*[^\s;]+"
    r")"
)


class FixtureError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def object_sha256(value: object) -> str:
    return sha256_text(canonical_json(value))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def memory_block(transaction_id: str, content: str, content_sha256: str) -> str:
    return "\n".join(
        [
            f"## Decretum Synthetic Memory: {transaction_id}",
            "",
            f"- content_sha256: {content_sha256}",
            f"- content: {content}",
            "- source: synthetic_native_store_fixture",
            "",
        ]
    )


def build_fixture(root: Path) -> dict[str, Any]:
    transaction_id = f"mem-pipeline-{uuid4().hex[:12]}"
    native_receipt_id = f"{transaction_id}-native"
    shared_receipt_id = f"{transaction_id}-shared"
    native_root = root / "synthetic-native-store"
    shared_root = root / "synthetic-shiguan" / "references"
    native_memory = native_root / "MEMORY.md"
    native_receipt_path = native_root / "court-memory" / "transactions" / f"{transaction_id}.json"
    shared_receipt_path = shared_root / "court-runtime" / "memory-pipeline" / "receipts" / f"{transaction_id}.json"
    registry_path = shared_root / "memory-decisions" / "synthetic-memory-registry.json"

    write_text(native_memory, "# Synthetic Native Memory\n\n")
    before_text = read_text(native_memory)
    before_sha256 = sha256_text(before_text)
    content_sha256 = sha256_text(CANDIDATE_CONTENT)

    scan_stage = {
        "name": "scan",
        "ok": True,
        "synthetic_native_store": True,
        "real_private_body_access": False,
        "native_before_sha256": before_sha256,
        "candidate_content_sha256": content_sha256,
    }

    has_secret = SECRET_RE.search(CANDIDATE_CONTENT) is not None
    decision = "SKIP" if has_secret else "WRITE"
    adjudicate_stage = {
        "name": "adjudicate",
        "ok": decision == "WRITE",
        "decision": decision,
        "secret_scan_passed": not has_secret,
        "fixture_review": "approved",
        "production_menxia_review": False,
        "reason": "synthetic low-risk durable rule candidate",
    }
    if decision != "WRITE":
        raise FixtureError("synthetic_candidate_rejected")

    after_text = before_text.rstrip() + "\n\n" + memory_block(transaction_id, CANDIDATE_CONTENT, content_sha256)
    write_text(native_memory, after_text)
    native_reread = read_text(native_memory)
    after_sha256 = sha256_text(native_reread)
    native_receipt = {
        "schema": "decretum.memory_pipeline_native_receipt.v1",
        "schema_version": 1,
        "receipt_id": native_receipt_id,
        "paired_shared_receipt_id": shared_receipt_id,
        "transaction_id": transaction_id,
        "stage": "apply",
        "synthetic_native_store": True,
        "real_memory_mutation": False,
        "candidate_content_sha256": content_sha256,
        "native_before_sha256": before_sha256,
        "native_after_sha256": after_sha256,
        "native_reread_sha256": after_sha256,
    }
    write_json(native_receipt_path, native_receipt)
    apply_stage = {
        "name": "apply",
        "ok": True,
        "native_receipt": native_receipt,
        "native_after_sha256": after_sha256,
        "write_target": "synthetic-native-store/MEMORY.md",
    }

    verify_stage = {
        "name": "verify",
        "ok": after_sha256 != before_sha256 and CANDIDATE_CONTENT in native_reread,
        "native_reread_sha256": after_sha256,
        "content_found": CANDIDATE_CONTENT in native_reread,
        "content_sha256_bound": content_sha256 in native_reread,
    }

    registry_entry = {
        "schema": "decretum.memory_pipeline_registry_entry.v1",
        "transaction_id": transaction_id,
        "memory_store_id": "synthetic-native-memory",
        "tool_class": "synthetic",
        "decision": decision,
        "candidate_content_sha256": content_sha256,
        "native_after_sha256": after_sha256,
        "native_receipt_id": native_receipt_id,
        "shared_receipt_id": shared_receipt_id,
    }
    registry = {
        "schema": "decretum.memory_pipeline_registry.v1",
        "schema_version": 1,
        "entries": [registry_entry],
    }
    write_json(registry_path, registry)
    shared_receipt = {
        "schema": "decretum.memory_pipeline_shared_receipt.v1",
        "schema_version": 1,
        "receipt_id": shared_receipt_id,
        "paired_native_receipt_id": native_receipt_id,
        "transaction_id": transaction_id,
        "stage": "reconcile",
        "synthetic_native_store": True,
        "real_memory_mutation": False,
        "candidate_content_sha256": content_sha256,
        "native_after_sha256": after_sha256,
        "native_receipt_sha256": object_sha256(native_receipt),
        "registry_entry_sha256": object_sha256(registry_entry),
    }
    write_json(shared_receipt_path, shared_receipt)
    reconcile_stage = {
        "name": "reconcile",
        "ok": True,
        "registry_entry": registry_entry,
        "shared_receipt": shared_receipt,
        "receipt_pair_verified": (
            native_receipt["receipt_id"] == shared_receipt["paired_native_receipt_id"]
            and shared_receipt["receipt_id"] == native_receipt["paired_shared_receipt_id"]
            and shared_receipt["native_receipt_sha256"] == object_sha256(native_receipt)
        ),
    }

    stages = [scan_stage, adjudicate_stage, apply_stage, verify_stage, reconcile_stage]
    return {
        "schema": SCHEMA,
        "schema_version": 1,
        "ok": all(stage["ok"] for stage in stages) and reconcile_stage["receipt_pair_verified"],
        "capability_claim": "PLANNED_UNVERIFIED_SYNTHETIC_ONLY",
        "generated_at": utc_now(),
        "pipeline": list(PIPELINE),
        "transaction_id": transaction_id,
        "fixture": {
            "synthetic_native_store": True,
            "real_memory_mutation": False,
            "real_private_body_access": False,
            "writes_codex_memory": False,
            "writes_hermes_memory": False,
            "writes_claude_memory": False,
        },
        "stages": stages,
        "artifacts": {
            "native_memory": "synthetic-native-store/MEMORY.md",
            "native_receipt": f"synthetic-native-store/court-memory/transactions/{transaction_id}.json",
            "shared_receipt": f"synthetic-shiguan/references/court-runtime/memory-pipeline/receipts/{transaction_id}.json",
            "registry": "synthetic-shiguan/references/memory-decisions/synthetic-memory-registry.json",
        },
    }


def run_fixture(fixture_root: Path | None = None) -> dict[str, Any]:
    if fixture_root is None:
        with tempfile.TemporaryDirectory(prefix="decretum-memory-pipeline-") as name:
            result = build_fixture(Path(name))
            result["fixture"]["retained"] = False
            return result
    if fixture_root.exists():
        raise FixtureError(f"fixture_root_already_exists:{fixture_root}")
    fixture_root.mkdir(parents=True)
    result = build_fixture(fixture_root)
    result["fixture"]["retained"] = True
    result["fixture"]["root"] = str(fixture_root)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)

    try:
        result = run_fixture(args.fixture_root)
    except FixtureError as exc:
        result = {"schema": SCHEMA, "schema_version": 1, "ok": False, "problem": str(exc)}
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"MEMORY_PIPELINE_FIXTURE ok={str(result.get('ok')).lower()}")
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())

