"""Verify native parallel execution is bound to real host actions and receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from court_native_execution import select_native_execution


BRIDGE_PATH = SCRIPTS / "court_native_host_dispatch.py"
RUNTIME_PATH = SCRIPTS / "court_runtime.py"
HOST_RECEIPT_SCHEMA = "court.native_host_action_receipt.v1"


def evaluate() -> dict[str, Any]:
    failures: list[str] = []
    execution = select_native_execution(
        authority="super",
        behavior="parallel",
        root=ROOT,
    ).as_dict()
    if execution.get("transport") == "spawned_subagent" and not execution.get(
        "host_action_receipt"
    ):
        failures.append("native_parallel_transport_unbound_to_host_receipt")

    bridge_exists = BRIDGE_PATH.is_file()
    if not bridge_exists:
        failures.extend(
            [
                "native_host_dispatch_bridge_missing",
                "native_reuse_followup_continuity_missing",
                "native_host_refusal_lifecycle_binding_missing",
            ]
        )

    runtime_source = RUNTIME_PATH.read_text(encoding="utf-8")
    if HOST_RECEIPT_SCHEMA not in runtime_source:
        failures.append("native_host_action_receipt_schema_missing")

    return {
        "schema": "court.native_host_dispatch_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "COURT_NATIVE_HOST_DISPATCH",
        "evidence": {
            "execution": execution,
            "bridge_path": str(BRIDGE_PATH),
            "bridge_exists": bridge_exists,
            "required_host_receipt_schema": HOST_RECEIPT_SCHEMA,
            "runtime_declares_host_receipt_schema": HOST_RECEIPT_SCHEMA in runtime_source,
            "required_host_actions": ["spawn", "reuse", "followup", "refusal"],
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, TypeError, ValueError) as exc:
        result = {
            "schema": "court.native_host_dispatch_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "COURT_NATIVE_HOST_DISPATCH",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"COURT_NATIVE_HOST_DISPATCH={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
