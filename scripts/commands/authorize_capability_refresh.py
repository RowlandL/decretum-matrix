"""Authorize one capability registry refresh (吏部/户部 authorization pass).

This is the **producer** half of the two-phase capability registry boundary. It
issues ``court.capability.refresh_transaction.v1`` with ``status: authorized``,
bound to the managed installation binding and to the exact source-path set of the
live capability scan.

The companion half is ``scripts/commands/refresh_capability_registry.py`` (the
consumer). It accepts ``authorized``/``pending``, performs the refresh, and is
what promotes the receipt to ``COMMITTED`` while writing the catalogs. This
command never writes the registry, and the refresh never authorizes itself, so
the two halves stay separable.

Usage:
  python -B scripts/authorize_capability_refresh.py --authority <who> --reason <why>
  python -B scripts/authorize_capability_refresh.py --authority <who> --reason <why> \\
      --apply --out <transaction.json>
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import json
from datetime import datetime, timezone

sys.dont_write_bytecode = True

from commands import refresh_capability_registry as registry  # noqa: E402
from court_capability_recruitment import (  # noqa: E402
    INSTALLATION_BINDING_SCHEMA,
    REFRESH_TRANSACTION_SCHEMA,
)

AUTHORIZED = "AUTHORIZED"


def build_transaction(
    *,
    authority: str,
    reason: str,
    generation: str,
    source_paths: list[str],
    installation_id: str,
    registry_path: str = "references/installed-capabilities-manifest.json",
) -> dict[str, object]:
    """Build the authorization receipt the refresh consumes."""

    timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    return {
        "schema": REFRESH_TRANSACTION_SCHEMA,
        "transaction_id": f"refresh-{generation}",
        "registry_generation": generation,
        "status": AUTHORIZED,
        "source_paths": source_paths,
        "registry_path": registry_path,
        "installation_id": installation_id,
        "authority": authority,
        "reason": reason,
        "authorized_at": timestamp,
        "started_at": timestamp,
        "completed_at": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="authorize-capability-refresh",
        description=(
            "Issue a court.capability.refresh_transaction.v1 authorization for one "
            "capability registry refresh. Does not write the registry."
        ),
    )
    parser.add_argument("--authority", required=True, help="Who authorizes this refresh (recorded verbatim).")
    parser.add_argument("--reason", required=True, help="Why this refresh is authorized (recorded verbatim).")
    parser.add_argument("--registry-generation", default=None, help="Explicit generation; default is minted.")
    parser.add_argument("--installation-binding", type=Path, default=None, help="Binding path; default is the managed one.")
    parser.add_argument("--out", default=None, help="Transaction output path (required with --apply).")
    parser.add_argument("--apply", action="store_true", help="Write the receipt; default is a read-only preview.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    home = registry.codex_home()
    managed = registry._managed_installation_binding_path(Path.home())
    binding_path = args.installation_binding if args.installation_binding is not None else managed
    binding = registry._load_reference_file(
        binding_path,
        INSTALLATION_BINDING_SCHEMA,
        expected_path=managed,
    )
    if binding is None:
        payload = {
            "schema": "court.capability.refresh_authorization.result.v1",
            "status": "BLOCKED",
            "reason": "INSTALLATION_BINDING_REQUIRED",
            "write_enabled": False,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else
              "CAPABILITY_REFRESH_AUTHORIZATION_BLOCKED reason=INSTALLATION_BINDING_REQUIRED")
        return 2

    binding_errors = registry.installation_binding_errors(binding, home_root=Path.home())
    installation_id = str(binding.get("installation_id") or "").strip()
    if binding_errors:
        payload = {
            "schema": "court.capability.refresh_authorization.result.v1",
            "status": "BLOCKED",
            "reason": "INSTALLATION_BINDING_INVALID",
            "errors": binding_errors,
            "write_enabled": False,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else
              "CAPABILITY_REFRESH_AUTHORIZATION_BLOCKED reason=INSTALLATION_BINDING_INVALID")
        return 2

    records = registry.collect_records(home)
    source_paths = registry.source_paths_of(records)
    generation = str(args.registry_generation or "").strip() or (
        "capgen-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    transaction = build_transaction(
        authority=args.authority,
        reason=args.reason,
        generation=generation,
        source_paths=source_paths,
        installation_id=installation_id,
    )

    written = None
    if args.apply:
        if not args.out:
            payload = {
                "schema": "court.capability.refresh_authorization.result.v1",
                "status": "BLOCKED",
                "reason": "OUT_REQUIRED_WITH_APPLY",
                "write_enabled": False,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else
                  "CAPABILITY_REFRESH_AUTHORIZATION_BLOCKED reason=OUT_REQUIRED_WITH_APPLY")
            return 2
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(transaction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written = str(out)

    payload = {
        "schema": "court.capability.refresh_authorization.result.v1",
        "status": AUTHORIZED if args.apply else "PREVIEW",
        "authority": args.authority,
        "reason": args.reason,
        "registry_generation": generation,
        "installation_id": installation_id,
        "records": len(records),
        "source_paths": len(source_paths),
        "transaction_id": transaction["transaction_id"],
        "written": written,
        "write_enabled": bool(args.apply),
        "next": (
            "python -B scripts/refresh_capability_registry.py --apply --yes "
            f"--refresh-transaction {written or '<out>'}"
        ),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"capability refresh authorization : {payload['status']}")
        print(f"  authority      : {args.authority}")
        print(f"  generation     : {generation}")
        print(f"  installation_id: {installation_id}")
        print(f"  records        : {len(records)}")
        print(f"  source_paths   : {len(source_paths)}")
        if written:
            print(f"  written        : {written}")
            print(f"  next           : {payload['next']}")
        else:
            print("  (preview only; rerun with --apply --out <path> to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
