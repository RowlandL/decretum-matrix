"""Regression checks for task-aware Codex office model routing."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
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


def main() -> int:
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
    require(repeat["model_route_id"] == lightweight["model_route_id"], "model route id must be deterministic")

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
    require(applied["model_override_applied"] is True, "proven host proof must apply the override")
    require(applied["model_route_status"] == "APPLIED", "proven host proof route status mismatch")
    require(applied["runtime_degraded"] is False, "proven host proof must not degrade")
    require(
        re.fullmatch(r"[0-9a-f]{64}", str(applied.get("host_proof_sha256") or "")),
        "host_proof_sha256 must be a SHA256 digest",
    )
    require(
        applied["host_proof_codex_version"] == "0.149.0-alpha.4.1",
        "host proof codex version binding mismatch",
    )
    repeated = route_office_model_with_host_proof(security, host_probe_ok)
    require(
        repeated["host_proof_sha256"] == applied["host_proof_sha256"],
        "host proof digest must be deterministic",
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
    require(
        worker_style["model_override_applied"] is True,
        "fresh-worker style proof (model_effort_pairs) must also apply",
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
        require(result["host_proof_sha256"] is None, f"{reason}: failed proof must not carry a digest")
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



