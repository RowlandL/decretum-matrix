"""Validate the synthetic native-memory pipeline fixture."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_pipeline_fixture import PIPELINE, object_sha256, run_fixture  # noqa: E402


def _stage_map(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stages = result.get("stages", [])
    if not isinstance(stages, list):
        return {}
    return {str(stage.get("name")): stage for stage in stages if isinstance(stage, dict)}


def run() -> dict[str, object]:
    result = run_fixture()
    stages = _stage_map(result)
    scan = stages.get("scan", {})
    apply = stages.get("apply", {})
    verify = stages.get("verify", {})
    reconcile = stages.get("reconcile", {})
    native_receipt = apply.get("native_receipt", {}) if isinstance(apply, dict) else {}
    shared_receipt = reconcile.get("shared_receipt", {}) if isinstance(reconcile, dict) else {}
    registry_entry = reconcile.get("registry_entry", {}) if isinstance(reconcile, dict) else {}
    checks = [
        ("schema", result.get("schema") == "decretum.memory_pipeline_fixture.v1"),
        ("fixture_ok", result.get("ok") is True),
        ("pipeline_order", result.get("pipeline") == list(PIPELINE)),
        (
            "synthetic_only",
            result.get("fixture", {}).get("synthetic_native_store") is True
            and result.get("fixture", {}).get("real_memory_mutation") is False,
        ),
        (
            "no_real_private_body_access",
            scan.get("real_private_body_access") is False
            and result.get("fixture", {}).get("real_private_body_access") is False,
        ),
        (
            "no_real_tool_memory_writes",
            result.get("fixture", {}).get("writes_codex_memory") is False
            and result.get("fixture", {}).get("writes_hermes_memory") is False
            and result.get("fixture", {}).get("writes_claude_memory") is False,
        ),
        (
            "apply_changed_native_content",
            isinstance(native_receipt, dict)
            and native_receipt.get("native_before_sha256") != native_receipt.get("native_after_sha256"),
        ),
        (
            "native_reread_bound",
            isinstance(native_receipt, dict)
            and native_receipt.get("native_after_sha256") == native_receipt.get("native_reread_sha256")
            and verify.get("native_reread_sha256") == native_receipt.get("native_after_sha256"),
        ),
        (
            "content_verified",
            verify.get("content_found") is True and verify.get("content_sha256_bound") is True,
        ),
        (
            "paired_receipts",
            isinstance(native_receipt, dict)
            and isinstance(shared_receipt, dict)
            and native_receipt.get("receipt_id") == shared_receipt.get("paired_native_receipt_id")
            and shared_receipt.get("receipt_id") == native_receipt.get("paired_shared_receipt_id")
            and shared_receipt.get("native_receipt_sha256") == object_sha256(native_receipt),
        ),
        (
            "registry_reconciled",
            isinstance(registry_entry, dict)
            and registry_entry.get("transaction_id") == result.get("transaction_id")
            and registry_entry.get("native_after_sha256") == native_receipt.get("native_after_sha256"),
        ),
        ("capability_not_promoted", result.get("capability_claim") == "PLANNED_UNVERIFIED_SYNTHETIC_ONLY"),
    ]
    return {
        "schema": "decretum.memory_pipeline_fixture_check.v1",
        "ok": all(ok for _, ok in checks),
        "checks": [{"name": name, "ok": ok} for name, ok in checks],
        "transaction_id": result.get("transaction_id"),
    }


def main() -> int:
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
