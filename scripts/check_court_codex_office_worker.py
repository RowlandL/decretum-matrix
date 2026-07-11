"""Focused checks for the fresh-session Codex office worker adapter."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True

from court_codex_office_worker import (
    HOST_PROOF_SCHEMA,
    build_worker_plan,
    verify_session_metadata,
)


def proof() -> dict[str, object]:
    return {
        "schema": HOST_PROOF_SCHEMA,
        "verified": True,
        "codex_version": "0.144.1",
        "binary_sha256": "a" * 64,
        "verified_at": "2026-07-11T09:00:00+08:00",
        "model_effort_pairs": [
            {"model": "gpt-5.6-luna", "effort": "max", "session_id": "019f4eae-7c0c-71c3-b992-e4cd83f21ae8"},
            {"model": "gpt-5.6-terra", "effort": "ultra", "session_id": "019f4eaf-96bc-74e3-88d0-0193926caf91"},
            {"model": "gpt-5.6-sol", "effort": "ultra", "session_id": "019f4eb0-38e7-7760-bbc9-77a030b7cf0e"},
        ],
    }


def plan_for(*, assignment: str, task_focus: str, complexity: str, risk: str, ambiguity: str) -> dict[str, object]:
    return build_worker_plan(
        role="hubu",
        assignment=assignment,
        task_focus=task_focus,
        complexity=complexity,
        risk=risk,
        ambiguity=ambiguity,
        prompt="Return a bounded office memorial.",
        sandbox="read-only",
        codex_executable="codex",
        native_codex_path=None,
        host_proof=proof(),
    )


def main() -> int:
    luna = plan_for(
        assignment="light clerical status",
        task_focus="轻量状态格式",
        complexity="low",
        risk="low",
        ambiguity="low",
    )
    assert luna["model"] == "gpt-5.6-luna"
    assert luna["reasoning_effort"] == "max"

    terra = plan_for(
        assignment="general implementation",
        task_focus="balanced coordination",
        complexity="medium",
        risk="medium",
        ambiguity="medium",
    )
    assert terra["model"] == "gpt-5.6-terra"
    assert terra["reasoning_effort"] == "ultra"

    sol = plan_for(
        assignment="security architecture final review",
        task_focus="credential threat model",
        complexity="critical",
        risk="high",
        ambiguity="high",
    )
    assert sol["model"] == "gpt-5.6-sol"
    assert sol["reasoning_effort"] == "ultra"
    assert sol["office_instance_kind"] == "fresh_codex_worker"
    assert sol["model_override_applied"] is True
    argv = list(sol["argv"])
    assert argv[:3] == ["codex", "exec", "--json"]
    assert "resume" not in argv and "--last" not in argv and "--ephemeral" not in argv
    assert argv[argv.index("-m") + 1] == "gpt-5.6-sol"
    assert argv[argv.index("-c") + 1] == 'model_reasoning_effort="ultra"'
    disabled = [argv[index + 1] for index, item in enumerate(argv[:-1]) if item == "--disable"]
    assert disabled == ["multi_agent_v2", "multi_agent"]

    bad = proof()
    bad["verified"] = False
    try:
        build_worker_plan(
            role="hubu",
            assignment="general implementation",
            task_focus="balanced coordination",
            complexity="medium",
            risk="medium",
            ambiguity="medium",
            prompt="bounded",
            sandbox="read-only",
            codex_executable="codex",
            native_codex_path=None,
            host_proof=bad,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("unverified host proof enabled a fresh worker")

    with tempfile.TemporaryDirectory() as temp_dir:
        session = Path(temp_dir) / "session.jsonl"
        session.write_text(
            "\n".join(
                [
                    json.dumps({"type": "session_meta", "payload": {"id": "019f4eb0-38e7-7760-bbc9-77a030b7cf0e", "model_provider": "custom"}}),
                    json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "ultra", "cwd": sol["dossier_dir"]}}),
                ]
            ),
            encoding="utf-8",
        )
        verified = verify_session_metadata(
            session,
            expected_session_id="019f4eb0-38e7-7760-bbc9-77a030b7cf0e",
            expected_model="gpt-5.6-sol",
            expected_effort="ultra",
            expected_cwd=Path(str(sol["dossier_dir"])),
        )
        assert verified["model_override_applied"] is True

        native = Path(temp_dir) / "codex.exe"
        native.write_bytes(b"host-proof-binary")
        native_proof = proof()
        import hashlib

        native_proof["binary_sha256"] = hashlib.sha256(native.read_bytes()).hexdigest()
        native_plan = build_worker_plan(
            role="hubu",
            assignment="general implementation",
            task_focus="balanced coordination",
            complexity="medium",
            risk="medium",
            ambiguity="medium",
            prompt="bounded",
            sandbox="read-only",
            codex_executable="codex",
            native_codex_path=native,
            host_proof=native_proof,
        )
        assert native_plan["native_codex_sha256"] == native_proof["binary_sha256"]
        assert native_plan["argv"][0] == str(native.resolve())
        try:
            build_worker_plan(
                role="hubu",
                assignment="general implementation",
                task_focus="balanced coordination",
                complexity="medium",
                risk="medium",
                ambiguity="medium",
                prompt="bounded",
                sandbox="read-only",
                codex_executable="codex",
                native_codex_path=native,
                host_proof=proof(),
            )
        except ValueError:
            pass
        else:
            raise AssertionError("stale binary proof was accepted")

    print("COURT_CODEX_OFFICE_WORKER_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
