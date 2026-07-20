"""Structured execution selection for the isolated superCC entry."""

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
class SuperCCExecution:
    authority: str
    behavior: str
    office_config: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "court.execution.supercc.v1",
            "authority": self.authority,
            "behavior": self.behavior,
            "runtime": "superCC",
            "entry_path": "supercc",
            "transport": "visible_zellij_squad",
            "state_namespace": "court.supercc.task",
            "office_config": dict(self.office_config),
        }


def select_supercc_execution(
    *,
    authority: str,
    behavior: str,
    root: Path | str = ROOT,
) -> SuperCCExecution:
    normalized_authority = str(authority).strip().casefold()
    normalized_behavior = str(behavior).strip().casefold()
    if normalized_authority not in AUTHORITIES:
        raise ValueError("authority_invalid")
    if normalized_behavior not in BEHAVIORS:
        raise ValueError("behavior_invalid")
    return SuperCCExecution(
        authority=normalized_authority,
        behavior=normalized_behavior,
        office_config=neutral_office_config(root),
    )
