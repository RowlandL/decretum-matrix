"""Structured execution selection for the native court entry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Mapping

sys.dont_write_bytecode = True

from court_office_config import ROOT, neutral_office_config


AUTHORITIES = frozenset({"approval", "autonomous", "super"})
BEHAVIORS = frozenset({"serial", "parallel"})


@dataclass(frozen=True)
class NativeExecution:
    authority: str
    behavior: str
    office_config: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "court.execution.native.v1",
            "authority": self.authority,
            "behavior": self.behavior,
            "runtime": "native",
            "entry_path": "court",
            "transport": "spawned_subagent" if self.behavior == "parallel" else "inline_serial",
            "state_namespace": "court.native.task",
            "office_config": dict(self.office_config),
        }


def select_native_execution(
    *,
    authority: str,
    behavior: str,
    root: Path | str = ROOT,
) -> NativeExecution:
    normalized_authority = str(authority).strip().casefold()
    normalized_behavior = str(behavior).strip().casefold()
    if normalized_authority not in AUTHORITIES:
        raise ValueError("authority_invalid")
    if normalized_behavior not in BEHAVIORS:
        raise ValueError("behavior_invalid")
    return NativeExecution(
        authority=normalized_authority,
        behavior=normalized_behavior,
        office_config=neutral_office_config(root),
    )
