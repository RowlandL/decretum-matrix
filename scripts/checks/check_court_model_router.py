"""Regression checks for task-aware Codex office model routing."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
from copy import deepcopy
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import json
import re
import sys

sys.dont_write_bytecode = True

from court_model_router import route_office_model, route_office_model_with_host_proof, validate_model_route_ack


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_value_error(callback, message: str) -> None:
    try:
        callback()
    except ValueError:
        return
    raise AssertionError(message)


def require_no_task_model_authority(value: dict[str, object], label: str) -> None:
    require(
        value.get("current_codex_model_selection") is None
        and value.get("model_execution_authorization") is None
        and value.get("model_authorization_binding") is None,
        f"{label}: router output created task model authority",
    )


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    model_contract = (root / "references" / "court-office-model-routing.md").read_text(
        encoding="utf-8"
    )
    dispatch_contract = (root / "references" / "court-offices-dispatch.md").read_text(
        encoding="utf-8"
    )
    model_contract_flat = " ".join(model_contract.split())
    dispatch_contract_flat = " ".join(dispatch_contract.split())
    current_host_contract = (
        "`spawn_agent_type_field=visible|hidden`",
        "`visible` binds only the exact admitted role",
        "When neither field is selected, model/effort behavior is absence and inheritance.",
        "`current_user_explicit`",
        "`spawn_model_field=visible|hidden`",
        "`spawn_reasoning_effort_field=visible|hidden`",
        "model-only, effort-only, or both",
        "host-default effort",
        "child `turn_context`",
        "A recommendation is not authorization.",
        "Missing selector preserves the legacy V1/V2 compatibility default.",
        "Historical V1 And Resume Limits On Codex 0.144.1",
    )
    missing_model_contract = [
        marker for marker in current_host_contract if marker not in model_contract_flat
    ]
    require(
        not missing_model_contract,
        "current capability-driven Codex host contract missing: "
        + ", ".join(missing_model_contract),
    )
    require(
        "`spawn_agent_type_field=visible|hidden`" in dispatch_contract_flat
        and "model/effort default to inheritance" in dispatch_contract_flat
        and "current_user_explicit" in dispatch_contract_flat
        and "child `turn_context`" in dispatch_contract_flat,
        "dispatch contract still presents the historical hidden-agent-type assumption as current",
    )

    security = route_office_model(
        transport="codex",
        role="xingbu",
        assignment="review credential handling",
        task_focus="security privacy and destructive-operation risk",
        complexity="medium",
        risk="high",
        ambiguity="medium",
    )
    require(security["recommended_model"] == "gpt-5.6-sol", "high-risk security work must recommend Sol")
    require(security["recommended_reasoning_effort"] == "ultra", "Sol recommendation must use its highest supported effort")
    require(security["supported_max_reasoning_effort"] == "ultra", "Sol maximum effort mismatch")
    require(security["model"] is None and security["reasoning_effort"] is None, "reserved V2 schema must not expose model overrides")
    require(security["model_override_applied"] is False, "reserved V2 schema must inherit the parent model")
    require_no_task_model_authority(security, "recommendation-only route")
    require(
        security["inheritance_policy"] == "inherit_main_thread_model_reserved_schema",
        "Codex reserved-schema inheritance policy mismatch",
    )
    require(
        not ({"agent_type", "model", "reasoning_effort"} & set(security["spawn_metadata"])),
        "reserved V2 spawn metadata leaked forbidden fields",
    )

    architecture = route_office_model(
        transport="codex",
        role="gongbu",
        assignment="split a monolith without semantic drift",
        task_focus="architecture and final integration",
        complexity="high",
        risk="medium",
        ambiguity="high",
    )
    require(architecture["recommended_model"] == "gpt-5.6-sol", "deep architecture work must recommend Sol")

    balanced = route_office_model(
        transport="codex",
        role="hubu",
        assignment="analyse measured runtime cost",
        task_focus="general quantitative review",
        complexity="medium",
        risk="medium",
        ambiguity="medium",
    )
    require(balanced["recommended_model"] == "gpt-5.6-terra", "balanced work must recommend Terra")
    require(balanced["recommended_reasoning_effort"] == "ultra", "Terra recommendation must use its highest supported effort")

    lightweight = route_office_model(
        transport="codex",
        role="shiguan",
        assignment="format an already approved status record",
        task_focus="light clerical formatting and status indexing",
        complexity="low",
        risk="low",
        ambiguity="low",
    )
    require(lightweight["recommended_model"] == "gpt-5.6-luna", "low-risk clerical work must recommend Luna")
    require(lightweight["recommended_reasoning_effort"] == "max", "Luna recommendation must use max, its highest supported effort")
    require(lightweight["supported_max_reasoning_effort"] == "max", "Luna maximum effort mismatch")

    repeat = route_office_model(
        transport="codex",
        role="shiguan",
        assignment="format an already approved status record",
        task_focus="light clerical formatting and status indexing",
        complexity="low",
        risk="low",
        ambiguity="low",
    )
    require(re.fullmatch(r"cmr-[0-9a-f]{8}", repeat["model_route_id"]), "model route naming style changed")
    require(repeat["model_route_id"] != lightweight["model_route_id"], "distinct route records need distinct handles")

    claude = route_office_model(
        transport="claude-code",
        role="menxia",
        assignment="review a plan",
        task_focus="standards review",
        complexity="high",
        risk="high",
        ambiguity="high",
    )
    require(claude["model"] is None and claude["reasoning_effort"] is None, "Claude must not receive model overrides")
    require(claude["model_override_applied"] is False, "Claude override boundary violated")
    require(claude["inheritance_policy"] == "inherit_main_thread_model", "Claude inheritance policy mismatch")

    hermes = route_office_model(
        transport="hermes",
        role="shiguan-hermes",
        assignment="record approved evidence",
        task_focus="archive semantics",
        complexity="medium",
        risk="medium",
        ambiguity="medium",
    )
    require(hermes["model"] is None and hermes["reasoning_effort"] is None, "Hermes must not receive model overrides")
    require(hermes["model_override_applied"] is False, "Hermes override boundary violated")
    require(hermes["inheritance_policy"] == "inherit_main_profile_model", "Hermes inheritance policy mismatch")
    require(hermes["future_review_required"] is True, "Hermes future design marker missing")

    codex_ack = {
        "model_route_id": security["model_route_id"],
        "model_override_applied": False,
        "inheritance_policy": "inherit_main_thread_model_reserved_schema",
    }
    validate_model_route_ack(security, codex_ack)
    expect_value_error(
        lambda: validate_model_route_ack(security, {**codex_ack, "model_override_applied": True}),
        "Codex reserved-schema override was accepted",
    )
    # A current-user-explicit selection is distinct from the router's
    # recommendation.  Only a capture-proved child turn context may make the
    # formal ACK report an applied override.
    for label, requested_model, requested_effort, expected_policy in (
        (
            "model-only",
            "gpt-6-astra",
            None,
            "explicit_model_host_default_effort",
        ),
        (
            "effort-only",
            None,
            "high",
            "inherit_model_explicit_effort",
        ),
        (
            "pair",
            "gpt-6-astra",
            "ultra",
            "explicit_model_and_effort",
        ),
    ):
        selection = {
            "schema": "court.codex.model_selection.v1",
            "selection_id": "MEA-" + ({"model-only": "1", "effort-only": "2", "pair": "3"}[label] * 32),
            "source": "current_user_explicit",
            "case_ref": {"court_code": "CFT-20260920-001-A001", "charter_revision": 1},
            "semantic_epoch": 1,
            "model": requested_model,
            "reasoning_effort": requested_effort,
        }
        applied_fields = [
            field
            for field, selected in (
                ("model", requested_model),
                ("reasoning_effort", requested_effort),
            )
            if selected is not None
        ]
        child_model = requested_model or "gpt-5.6-sol"
        child_effort = (
            requested_effort
            if requested_effort is not None
            else ("low" if requested_model is not None else "ultra")
        )
        host_binding = {
            "schema": "court.host_model_execution_binding.v1",
            "selection_id": selection["selection_id"],
            "applied_spawn_fields": applied_fields,
            "parent_turn_context": {
                "model": "gpt-5.6-sol", "effort": "ultra",
                "trace_line": 2, "turn_id": "parent-turn-001",
            },
            "child_turn_context": {
                "model": child_model, "effort": child_effort,
                "trace_line": 2, "turn_id": "child-turn-001",
            },
            "status": "MATCHED",
        }
        explicit_route = {
            **security,
            "model_authorization_binding": selection,
            "host_model_execution_binding": host_binding,
        }
        explicit_ack = {
            "model_route_id": security["model_route_id"],
            "model_selection_id": selection["selection_id"],
            "active_model": child_model,
            "active_reasoning_effort": child_effort,
            "model_override_applied": True,
            "inheritance_policy": expected_policy,
        }
        validate_model_route_ack(explicit_route, explicit_ack)
        foreign_effort = "medium" if child_effort != "medium" else "low"
        for field, invalid in (
            ("model_selection_id", "MEA-" + "f" * 32),
            ("active_model", "foreign-model"),
            ("active_reasoning_effort", foreign_effort),
            ("model_override_applied", False),
            ("inheritance_policy", "inherit_main_thread_model_reserved_schema"),
        ):
            expect_value_error(
                lambda field=field, invalid=invalid: validate_model_route_ack(
                    explicit_route,
                    {**explicit_ack, field: invalid},
                ),
                f"{label} explicit ACK accepted invalid {field}",
            )
        for context_field, forged_value, ack_field in (
            ("model", "gpt-forged-model", "active_model"),
            ("effort", "low", "active_reasoning_effort"),
        ):
            if label == "model-only" and context_field == "effort":
                continue
            forged_binding = deepcopy(host_binding)
            forged_binding["child_turn_context"][context_field] = forged_value
            forged_route = {
                **explicit_route,
                "host_model_execution_binding": forged_binding,
            }
            forged_ack = {**explicit_ack, ack_field: forged_value}
            expect_value_error(
                lambda forged_route=forged_route, forged_ack=forged_ack: (
                    validate_model_route_ack(forged_route, forged_ack)
                ),
                f"{label} explicit ACK accepted authorization drift in {context_field}",
            )
    v1_security = route_office_model(
        transport="codex",
        protocol="v1",
        role="xingbu",
        assignment="review credential handling",
        task_focus="security privacy and destructive-operation risk",
        complexity="medium",
        risk="high",
        ambiguity="medium",
    )
    require(v1_security["protocol"] == "v1", "V1 protocol marker missing")
    require(v1_security["model_override_applied"] is False, "pre-spawn V1 route cannot claim applied")
    require(
        v1_security["spawn_metadata"]
        == {
            "agent_type": "xingbu",
            "fork_turns": "none",
        },
        "V1 host metadata must bind the office without claiming model/effort injection",
    )
    validate_model_route_ack(
        v1_security,
        {
            "model_route_id": v1_security["model_route_id"],
            "model_override_applied": False,
            "inheritance_policy": "inherit_main_thread_model_v1_agent_type",
        },
    )
    for mutation in (
        {"model_override_applied": True},
        {"inheritance_policy": "v1_host_override_verified"},
    ):
        valid_v1_ack = {
            "model_route_id": v1_security["model_route_id"],
            "model_override_applied": False,
            "inheritance_policy": "inherit_main_thread_model_v1_agent_type",
        }
        expect_value_error(
            lambda mutation=mutation: validate_model_route_ack(v1_security, {**valid_v1_ack, **mutation}),
            f"invalid V1 override ack accepted: {mutation}",
        )
    validate_model_route_ack(
        claude,
        {
            "model_route_id": claude["model_route_id"],
            "model_override_applied": False,
            "inheritance_policy": "inherit_main_thread_model",
        },
    )
    validate_model_route_ack(
        hermes,
        {
            "model_route_id": hermes["model_route_id"],
            "model_override_applied": False,
            "inheritance_policy": "inherit_main_profile_model",
        },
    )

    # ---- P4-2 host-proof binding (contract-c) ----
    host_probe_ok = {
        "codex_version": "0.149.0-alpha.4.1",
        "codex_executable": "$CODEX_HOME/plugins/.plugin-appserver/codex.exe",
        "supported_model_effort_pairs": [
            {"model": "gpt-5.6-luna", "effort": "max"},
            {"model": "gpt-5.6-terra", "effort": "ultra"},
            {"model": "gpt-5.6-sol", "effort": "ultra"},
        ],
        "config_exposes_model": True,
        "turn_context_model": "gpt-5.6-sol",
        "turn_context_effort": "ultra",
    }
    applied = route_office_model_with_host_proof(security, host_probe_ok)
    require_no_task_model_authority(applied, "host-proof route")
    require(applied["model_override_applied"] is True, "proven host proof must apply the override")
    require(applied["model_route_status"] == "APPLIED", "proven host proof route status mismatch")
    require(applied["runtime_degraded"] is False, "proven host proof must not degrade")
    require(
        applied.get("host_proof_reference") == host_probe_ok,
        "host proof must preserve actual observed evidence",
    )
    require(
        applied["host_proof_codex_version"] == "0.149.0-alpha.4.1",
        "host proof codex version binding mismatch",
    )
    repeated = route_office_model_with_host_proof(security, host_probe_ok)
    require(
        repeated["host_proof_reference"] == applied["host_proof_reference"],
        "the same host evidence must remain structurally equal",
    )

    worker_style_probe = {
        "codex_version": "0.149.0-alpha.4.1",
        "model_effort_pairs": [
            {"model": "gpt-5.6-luna", "effort": "max"},
            {"model": "gpt-5.6-sol", "effort": "ultra"},
            {"model": "gpt-5.6-terra", "effort": "ultra"},
        ],
        "turn_context_model": "gpt-5.6-sol",
        "turn_context_effort": "ultra",
    }
    worker_style = route_office_model_with_host_proof(security, worker_style_probe)
    require_no_task_model_authority(worker_style, "fresh-worker host-proof route")
    require(
        worker_style["model_override_applied"] is True,
        "fresh-worker style proof (model_effort_pairs) must also apply",
    )

    needs_like_probe = {
        **host_probe_ok,
        "host_managed_recommendation": {
            "model": security["recommended_model"],
            "reasoning_effort": security["recommended_reasoning_effort"],
        },
        "needs_model_override": True,
        "needs_reasoning_effort_override": True,
    }
    needs_like = route_office_model_with_host_proof(security, needs_like_probe)
    require_no_task_model_authority(
        needs_like,
        "host recommendation and needs-like inputs",
    )

    def expect_fallback(probe: object, reason: str) -> dict[str, object]:
        result = route_office_model_with_host_proof(security, probe)  # type: ignore[arg-type]
        require(
            result["model_override_applied"] is False,
            f"{reason}: override must not be applied",
        )
        require(
            result["model_route_status"] == "FAILED",
            f"{reason}: route status must be FAILED",
        )
        require(result["runtime_degraded"] is True, f"{reason}: must be runtime_degraded")
        require(
            result["fallback"] == "inherit_parent_model_and_effort",
            f"{reason}: fallback must be inherit_parent_model_and_effort",
        )
        require("host_proof_reference" not in result, f"{reason}: failed proof must not be accepted")
        return result

    expect_fallback(None, "missing host proof")
    expect_fallback({}, "empty host proof")
    expect_fallback({**host_probe_ok, "codex_version": ""}, "missing codex version")
    expect_fallback(
        {**host_probe_ok, "supported_model_effort_pairs": [{"model": "gpt-5.6-luna", "effort": "max"}]},
        "unsupported recommended pair",
    )
    expect_fallback(
        {**host_probe_ok, "turn_context_model": None, "turn_context_effort": None},
        "missing turn context",
    )
    expect_fallback(
        {**host_probe_ok, "turn_context_model": "gpt-5.6-luna", "turn_context_effort": "max"},
        "turn context mismatch",
    )

    claude_bound = route_office_model_with_host_proof(claude, host_probe_ok)
    require(
        claude_bound["model_route_status"] == "INHERIT",
        "explicit-inheritance transport must stay INHERIT, not FAILED",
    )
    require(claude_bound["runtime_degraded"] is False, "explicit inheritance must not degrade")
    require(claude_bound["model_override_applied"] is False, "explicit inheritance must not apply")
    expect_value_error(
        lambda: route_office_model_with_host_proof("not-a-route", host_probe_ok),  # type: ignore[arg-type]
        "invalid route object was accepted",
    )
    expect_value_error(
        lambda: route_office_model(
            transport="unknown",
            role="xingbu",
            assignment="x",
            task_focus="x",
            complexity="low",
            risk="low",
            ambiguity="low",
        ),
        "unknown transport was accepted",
    )
    expect_value_error(
        lambda: route_office_model(
            transport="codex",
            protocol="v3",
            role="xingbu",
            assignment="x",
            task_focus="x",
            complexity="low",
            risk="low",
            ambiguity="low",
        ),
        "unknown protocol was accepted",
    )

    print(
        json.dumps(
            {
                "ok": True,
                "routes": {
                    "security": [security["recommended_model"], security["recommended_reasoning_effort"]],
                    "balanced": [balanced["recommended_model"], balanced["recommended_reasoning_effort"]],
                    "lightweight": [lightweight["recommended_model"], lightweight["recommended_reasoning_effort"]],
                    "claude": claude["inheritance_policy"],
                    "hermes": hermes["inheritance_policy"],
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
