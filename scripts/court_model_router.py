"""Deterministic task-aware model recommendations for court office agents.

Codex Multi-Agent V2 uses a model-reserved `collaboration.spawn_agent` schema.
Its default compatible shape hides `agent_type`, `model`, and
`reasoning_effort`, so the router records a task-aware recommendation but the
model-visible spawn inherits its parent model and effort. Claude Code and
Hermes likewise remain model-neutral and inherit their parent/main settings.
"""

from __future__ import annotations

import hashlib
import json
import zlib
from typing import Mapping


MODEL_ROUTE_SCHEMA = "court.office.model_route.v2"
EVALUATION_LEVELS = frozenset({"low", "medium", "high", "critical"})
TRANSPORTS = frozenset({"codex", "claude-code", "hermes"})
MODEL_MAX_REASONING_EFFORT = {
    "gpt-5.6-sol": "ultra",
    "gpt-5.6-terra": "ultra",
    "gpt-5.6-luna": "max",
}

_HIGH_STAKES_TERMS = (
    "architecture",
    "credential",
    "critical",
    "destructive",
    "final integration",
    "final review",
    "privacy",
    "rollback",
    "secret",
    "security",
    "semantic drift",
    "system design",
    "threat",
    "安全",
    "凭据",
    "架构",
    "隐私",
    "破坏",
    "语义漂移",
    "最终集成",
)
_LIGHTWEIGHT_TERMS = (
    "clerical",
    "formatting",
    "indexing",
    "light",
    "status",
    "template fill",
    "轻量",
    "格式",
    "索引",
    "状态",
    "文书",
)


def _required_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _level(value: object, field: str) -> str:
    level = _required_text(value, field).lower()
    if level not in EVALUATION_LEVELS:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(EVALUATION_LEVELS))}")
    return level


def _transport(value: object) -> str:
    transport = _required_text(value, "transport").lower()
    aliases = {"claude": "claude-code", "codex-cli": "codex"}
    transport = aliases.get(transport, transport)
    if transport not in TRANSPORTS:
        raise ValueError(f"unknown office transport: {transport}")
    return transport


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def _route_id(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"cmr-{zlib.crc32(canonical.encode('utf-8')):08x}"


def route_office_model(
    *,
    transport: str,
    protocol: str = "v2",
    role: str,
    assignment: str,
    task_focus: str,
    complexity: str,
    risk: str,
    ambiguity: str,
) -> dict[str, object]:
    """Return a deterministic model decision and its enforcement contract."""

    normalized_transport = _transport(transport)
    normalized_protocol = _required_text(protocol, "protocol").lower()
    if normalized_protocol not in {"v1", "v2"}:
        raise ValueError("protocol must be v1 or v2")
    normalized_role = _required_text(role, "role").lower()
    normalized_assignment = _required_text(assignment, "assignment")
    normalized_focus = _required_text(task_focus, "task_focus")
    normalized_complexity = _level(complexity, "complexity")
    normalized_risk = _level(risk, "risk")
    normalized_ambiguity = _level(ambiguity, "ambiguity")
    evaluation = {
        "complexity": normalized_complexity,
        "risk": normalized_risk,
        "ambiguity": normalized_ambiguity,
    }
    identity = {
        "schema": MODEL_ROUTE_SCHEMA,
        "transport": normalized_transport,
        "protocol": normalized_protocol,
        "role": normalized_role,
        "assignment": normalized_assignment,
        "task_focus": normalized_focus,
        **evaluation,
    }

    if normalized_transport == "claude-code":
        decision = {
            **identity,
            "model": None,
            "reasoning_effort": None,
            "recommended_model": None,
            "recommended_reasoning_effort": None,
            "supported_max_reasoning_effort": None,
            "model_override_applied": False,
            "inheritance_policy": "inherit_main_thread_model",
            "enforcement": "transport_inheritance_required",
            "future_review_required": False,
            "decision_basis": ["claude_code_model_configuration_out_of_scope"],
            "spawn_metadata": {"agent_type": normalized_role, "fork_turns": "none"},
        }
    elif normalized_transport == "hermes":
        decision = {
            **identity,
            "model": None,
            "reasoning_effort": None,
            "recommended_model": None,
            "recommended_reasoning_effort": None,
            "supported_max_reasoning_effort": None,
            "model_override_applied": False,
            "inheritance_policy": "inherit_main_profile_model",
            "enforcement": "transport_inheritance_required",
            "future_review_required": True,
            "decision_basis": ["hermes_profile_model_design_deferred"],
            "spawn_metadata": {"agent_type": normalized_role, "fork_turns": "none"},
        }
    else:
        assessment_text = f"{normalized_assignment}\n{normalized_focus}"
        high_stakes_focus = _contains_any(assessment_text, _HIGH_STAKES_TERMS)
        critical_dimension = "critical" in evaluation.values()
        deep_dimension = normalized_complexity == "high" or normalized_ambiguity == "high"
        high_risk = normalized_risk == "high"
        lightweight_focus = _contains_any(assessment_text, _LIGHTWEIGHT_TERMS)
        all_low = all(value == "low" for value in evaluation.values())

        basis: list[str] = []
        if critical_dimension:
            basis.append("critical_evaluation_dimension")
        if high_risk:
            basis.append("high_risk")
        if deep_dimension:
            basis.append("deep_or_ambiguous_work")
        if high_stakes_focus:
            basis.append("high_stakes_task_focus")

        if critical_dimension or high_risk or deep_dimension or high_stakes_focus:
            model = "gpt-5.6-sol"
            if not basis:
                basis.append("frontier_default")
        elif all_low and lightweight_focus:
            model = "gpt-5.6-luna"
            basis = ["low_complexity_risk_ambiguity", "lightweight_task_focus"]
        else:
            model = "gpt-5.6-terra"
            basis = ["balanced_general_work"]

        max_effort = MODEL_MAX_REASONING_EFFORT[model]
        common = {
            **identity,
            "model": None,
            "reasoning_effort": None,
            "recommended_model": model,
            "recommended_reasoning_effort": max_effort,
            "supported_max_reasoning_effort": max_effort,
            "model_override_applied": False,
            "future_review_required": True,
            "host_managed_recommendation": {
                "agent_type": normalized_role,
                "model": model,
                "reasoning_effort": max_effort,
            },
        }
        if normalized_protocol == "v1":
            decision = {
                **common,
                "inheritance_policy": "inherit_main_thread_model_v1_agent_type",
                "enforcement": "v1_agent_type_only_model_inheritance_required",
                "decision_basis": [*basis, "v1_agent_type_only_model_inheritance"],
                "spawn_metadata": {
                    "agent_type": normalized_role,
                    "fork_turns": "none",
                },
            }
        else:
            decision = {
                **common,
                "inheritance_policy": "inherit_main_thread_model_reserved_schema",
                "enforcement": "reserved_spawn_schema_inheritance_required",
                "decision_basis": [*basis, "reserved_spawn_schema_requires_hidden_metadata"],
                "spawn_metadata": {"fork_turns": "none"},
            }

    decision["model_route_id"] = _route_id(decision)
    return decision


def validate_model_route_ack(route: Mapping[str, object], ack: Mapping[str, object]) -> dict[str, object]:
    """Validate that the child reports the routed model or required inheritance."""

    expected_route_id = route.get("model_route_id")
    mismatched: list[str] = []
    if ack.get("model_route_id") != expected_route_id:
        mismatched.append("model_route_id")

    transport = str(route.get("transport") or "")
    protocol = str(route.get("protocol") or "v2")
    if transport == "codex":
        expected = {
            "model_override_applied": False,
            "inheritance_policy": route.get("inheritance_policy"),
        }
    elif transport in {"claude-code", "hermes"}:
        expected = {
            "model_override_applied": False,
            "inheritance_policy": route.get("inheritance_policy"),
        }
    else:
        raise ValueError(f"unsupported model route transport: {transport}")

    for key, value in expected.items():
        if ack.get(key) != value:
            mismatched.append(key)
    if mismatched:
        raise ValueError("model route ack mismatch: " + ", ".join(sorted(set(mismatched))))
    return dict(ack)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def route_office_model_with_host_proof(
    route: Mapping[str, object],
    host_probe: Mapping[str, object] | None,
) -> dict[str, object]:
    """Bind a task-aware route to a host probe; apply only on proven override.

    A satisfied host proof (version-bound executable plus supported
    model/effort pairs plus a consistent fresh-session turn-context read-back)
    yields ``model_override_applied=YES`` with ``host_proof_sha256``. Any
    missing or inconsistent proof falls back to
    ``inherit_parent_model_and_effort`` with ``model_route_status=FAILED`` and
    ``runtime_degraded=true`` — the router never fakes an applied override.
    Explicit-inheritance transports (Claude Code / Hermes, or a Codex route
    without a recommendation) keep their inheritance contract as ``INHERIT``,
    which is not a failure.
    """
    if not isinstance(route, Mapping):
        raise ValueError("route must be a model route object")
    base = dict(route)
    transport = str(route.get("transport") or "")
    recommended = route.get("recommended_model")
    effort = route.get("recommended_reasoning_effort")
    if transport != "codex" or recommended in (None, "") or effort in (None, ""):
        return {
            **base,
            "model_override_applied": False,
            "host_proof_sha256": None,
            "host_proof_codex_version": None,
            "model_route_status": "INHERIT",
            "runtime_degraded": False,
            "decision_basis": [*list(base.get("decision_basis") or []), "explicit_inheritance_kept"],
            "errors": [],
        }
    errors: list[str] = []
    if host_probe is None or not isinstance(host_probe, Mapping):
        errors.append("host_probe_missing")
        host_probe = {}
    codex_version = str(host_probe.get("codex_version") or "").strip()
    if not codex_version:
        errors.append("host_probe_missing_codex_version")
    raw_pairs = host_probe.get("supported_model_effort_pairs")
    if not isinstance(raw_pairs, list):
        raw_pairs = host_probe.get("model_effort_pairs")  # fresh-worker proof compatibility
    pair_set: set[tuple[str, str]] = set()
    if isinstance(raw_pairs, list):
        for raw in raw_pairs:
            if isinstance(raw, Mapping):
                pair_set.add((str(raw.get("model") or ""), str(raw.get("effort") or "")))
    recommended_text = str(recommended)
    effort_text = str(effort)
    if (recommended_text, effort_text) not in pair_set:
        errors.append("recommended_pair_not_supported_by_host")
    turn_model = host_probe.get("turn_context_model")
    turn_effort = host_probe.get("turn_context_effort")
    turn_present = turn_model is not None or turn_effort is not None
    if not turn_present:
        errors.append("host_probe_missing_turn_context")
    elif str(turn_model or "") != recommended_text or str(turn_effort or "") != effort_text:
        errors.append("turn_context_mismatch")
    proof_scope = {
        "codex_version": codex_version,
        "model_effort_pairs": sorted(pair_set),
        "turn_context_model": turn_model,
        "turn_context_effort": turn_effort,
    }
    proof_digest = hashlib.sha256(_canonical_json(proof_scope)).hexdigest()
    if not errors:
        return {
            **base,
            "model_override_applied": True,
            "host_proof_sha256": proof_digest,
            "host_proof_codex_version": codex_version,
            "model_route_status": "APPLIED",
            "runtime_degraded": False,
            "decision_basis": [*list(base.get("decision_basis") or []), "host_proof_applied"],
            "errors": [],
        }
    return {
        **base,
        "model_override_applied": False,
        "host_proof_sha256": None,
        "host_proof_codex_version": codex_version or None,
        "model_route_status": "FAILED",
        "runtime_degraded": True,
        "fallback": "inherit_parent_model_and_effort",
        "decision_basis": [*list(base.get("decision_basis") or []), "host_proof_fallback"],
        "errors": errors,
    }
