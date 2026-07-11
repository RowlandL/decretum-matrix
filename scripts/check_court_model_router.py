"""Regression checks for task-aware Codex office model routing."""

from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True

from court_model_router import route_office_model, validate_model_route_ack


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
