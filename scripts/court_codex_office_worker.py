"""Launch a fresh Codex office worker with host-verified top-level model routing.

This is deliberately separate from Multi-Agent V1/V2 child spawning. It never
claims a same-session protocol switch or a reserved-schema child override.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any
import uuid

sys.dont_write_bytecode = True

from court_model_router import MODEL_MAX_REASONING_EFFORT, route_office_model
from court_office_bootstrap import build_preload_manifest


HOST_PROOF_SCHEMA = "court.codex_fresh_worker_host_proof.v1"
WORKER_SCHEMA = "court.codex_fresh_worker.v1"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
ALLOWED_SANDBOXES = frozenset({"read-only", "workspace-write"})
REPO_ROOT = Path(__file__).resolve().parents[1]


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _bounded(value: object, field: str, *, maximum: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or "\x00" in text:
        raise ValueError(f"{field} must be bounded non-empty text")
    return text


def _canonical_uuid(value: object, field: str) -> str:
    text = str(value or "").strip().lower()
    try:
        canonical = str(uuid.UUID(text))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field} must be a canonical UUID") from exc
    if canonical != text:
        raise ValueError(f"{field} must be a canonical UUID")
    return canonical


def _canonical_sha256(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not SHA256_RE.fullmatch(text):
        raise ValueError(f"{field} must be a SHA256 digest")
    return text.lower()


def validate_host_proof(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("schema") != HOST_PROOF_SCHEMA:
        raise ValueError("fresh-worker host proof schema mismatch")
    if value.get("verified") is not True:
        raise ValueError("fresh-worker host proof is not verified")
    version = _bounded(value.get("codex_version"), "codex_version", maximum=64)
    binary_sha256 = _canonical_sha256(value.get("binary_sha256"), "binary_sha256")
    verified_at = _bounded(value.get("verified_at"), "verified_at", maximum=64)
    try:
        parsed = datetime.fromisoformat(verified_at)
    except ValueError as exc:
        raise ValueError("verified_at must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("verified_at must include a timezone offset")
    raw_pairs = value.get("model_effort_pairs")
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise ValueError("host proof must contain model_effort_pairs")
    pairs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_pairs:
        if not isinstance(raw, dict):
            raise ValueError("host proof model pair must be an object")
        model = _bounded(raw.get("model"), "proof.model", maximum=128)
        effort = _bounded(raw.get("effort"), "proof.effort", maximum=32)
        if MODEL_MAX_REASONING_EFFORT.get(model) != effort:
            raise ValueError("host proof model/effort pair is unsupported")
        pair = (model, effort)
        if pair in seen:
            raise ValueError("host proof contains duplicate model/effort pairs")
        seen.add(pair)
        pairs.append(
            {
                "model": model,
                "effort": effort,
                "session_id": _canonical_uuid(raw.get("session_id"), "proof.session_id"),
            }
        )
    normalized = {
        "schema": HOST_PROOF_SCHEMA,
        "verified": True,
        "codex_version": version,
        "binary_sha256": binary_sha256,
        "verified_at": verified_at,
        "model_effort_pairs": pairs,
    }
    normalized["proof_sha256"] = hashlib.sha256(_canonical_json(normalized)).hexdigest()
    return normalized


def build_worker_plan(
    *,
    role: str,
    assignment: str,
    task_focus: str,
    complexity: str,
    risk: str,
    ambiguity: str,
    prompt: str,
    sandbox: str,
    codex_executable: str,
    native_codex_path: Path | None,
    host_proof: dict[str, object],
) -> dict[str, object]:
    normalized_proof = validate_host_proof(host_proof)
    executable = _bounded(codex_executable, "codex_executable", maximum=1024)
    bounded_prompt = _bounded(prompt, "prompt", maximum=16000)
    sandbox_mode = _bounded(sandbox, "sandbox", maximum=32).lower()
    if sandbox_mode not in ALLOWED_SANDBOXES:
        raise ValueError("fresh office worker sandbox must be read-only or workspace-write")
    route = route_office_model(
        transport="codex",
        protocol="v2",
        role=role,
        assignment=assignment,
        task_focus=task_focus,
        complexity=complexity,
        risk=risk,
        ambiguity=ambiguity,
    )
    model = str(route.get("recommended_model") or "")
    effort = str(route.get("recommended_reasoning_effort") or "")
    proved_pairs = {
        (str(item["model"]), str(item["effort"]))
        for item in normalized_proof["model_effort_pairs"]  # type: ignore[index]
    }
    if (model, effort) not in proved_pairs:
        raise ValueError("recommended model/effort pair lacks host proof")
    manifest = build_preload_manifest(str(role).strip().lower())
    dossier_file = (REPO_ROOT / Path(manifest.dossier_path)).resolve()
    try:
        dossier_file.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("office dossier locator escaped the repository root") from exc
    dossier_dir = str(dossier_file.parent)
    native_path_text: str | None = None
    native_sha256: str | None = None
    if native_codex_path is not None:
        native_path = Path(native_codex_path).expanduser().resolve()
        info = native_path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError("native Codex path must be a strict regular file")
        native_sha256 = hashlib.sha256(native_path.read_bytes()).hexdigest()
        if native_sha256 != normalized_proof["binary_sha256"]:
            raise ValueError("native Codex binary does not match the host proof")
        native_path_text = str(native_path)
    argv = (
        native_path_text or executable,
        "exec",
        "--json",
        "--disable",
        "multi_agent_v2",
        "--disable",
        "multi_agent",
        "--skip-git-repo-check",
        "--sandbox",
        sandbox_mode,
        "-C",
        dossier_dir,
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        bounded_prompt,
    )
    if any(item in {"resume", "--last", "--ephemeral"} for item in argv):
        raise ValueError("fresh office worker must not resume or use implicit session selectors")
    return {
        "schema": WORKER_SCHEMA,
        "office_instance_kind": "fresh_codex_worker",
        "role": manifest.role_key,
        "office_zh": manifest.office_zh,
        "direct_superior": manifest.direct_superior,
        "dossier_dir": dossier_dir,
        "dossier_locator": manifest.dossier_path,
        "dossier_hash": manifest.dossier_hash,
        "profile_hash": manifest.profile_hash,
        "court_skill_hash": manifest.court_skill_hash,
        "model_route_id": route["model_route_id"],
        "model": model,
        "reasoning_effort": effort,
        "model_override_applied": True,
        "inheritance_policy": "fresh_session_top_level_host_override_verified",
        "host_proof_sha256": normalized_proof["proof_sha256"],
        "host_proof_codex_version": normalized_proof["codex_version"],
        "host_proof_binary_sha256": normalized_proof["binary_sha256"],
        "native_codex_path": native_path_text,
        "native_codex_sha256": native_sha256,
        "sandbox": sandbox_mode,
        "argv": argv,
    }


def _strict_session_lines(path: Path) -> list[str]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("session metadata source must be a strict regular file")
    if info.st_size > 64 * 1024 * 1024:
        raise ValueError("session metadata source is too large")
    return path.read_text(encoding="utf-8").splitlines()


def verify_session_metadata(
    path: Path,
    *,
    expected_session_id: str,
    expected_model: str,
    expected_effort: str,
    expected_cwd: Path,
) -> dict[str, object]:
    session_id = _canonical_uuid(expected_session_id, "expected_session_id")
    expected_cwd_resolved = expected_cwd.resolve()
    actual_session = actual_model = actual_effort = actual_cwd = provider = None
    for line in _strict_session_lines(path):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = item.get("payload") if isinstance(item, dict) and isinstance(item.get("payload"), dict) else {}
        if item.get("type") == "session_meta":
            actual_session = payload.get("id")
            provider = payload.get("model_provider")
        elif item.get("type") == "turn_context":
            actual_model = payload.get("model")
            actual_effort = payload.get("effort")
            actual_cwd = payload.get("cwd")
            break
    if str(actual_session or "").lower() != session_id:
        raise ValueError("fresh worker session id evidence mismatch")
    if actual_model != expected_model or actual_effort != expected_effort:
        raise ValueError("fresh worker model/effort evidence mismatch")
    if Path(str(actual_cwd or "")).resolve() != expected_cwd_resolved:
        raise ValueError("fresh worker dossier cwd evidence mismatch")
    return {
        "session_id": session_id,
        "model": actual_model,
        "reasoning_effort": actual_effort,
        "model_provider": provider,
        "dossier_dir": str(expected_cwd_resolved),
        "session_path": str(path.resolve()),
        "model_override_applied": True,
    }


def _parse_exec_output(stdout: str) -> tuple[str, str]:
    session_id = ""
    final_text = ""
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            session_id = str(event.get("thread_id") or "")
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            final_text = str(item.get("text") or "")
    return _canonical_uuid(session_id, "worker session_id"), final_text


def _session_path(session_id: str, codex_home: Path | None = None) -> Path:
    root = (codex_home or Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))).resolve()
    matches = list((root / "sessions").rglob(f"*{session_id}.jsonl"))
    if len(matches) != 1:
        raise ValueError("fresh worker session metadata file is not unique")
    return matches[0]


def run_worker(plan: dict[str, object], *, timeout_seconds: int = 600) -> dict[str, object]:
    if plan.get("schema") != WORKER_SCHEMA or plan.get("model_override_applied") is not True:
        raise ValueError("invalid fresh worker plan")
    timeout = int(timeout_seconds)
    if timeout < 1 or timeout > 3600:
        raise ValueError("fresh worker timeout must be between 1 and 3600 seconds")
    native_path = plan.get("native_codex_path")
    if not native_path:
        raise ValueError("fresh worker execution requires an exact native Codex path")
    current_native_sha256 = hashlib.sha256(Path(str(native_path)).read_bytes()).hexdigest()
    if current_native_sha256 != plan.get("host_proof_binary_sha256"):
        raise ValueError("fresh worker native Codex binary changed after planning")
    version_check = subprocess.run(
        [str(plan["argv"][0]), "--version"],  # type: ignore[index]
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if version_check.returncode != 0:
        raise RuntimeError("fresh worker Codex version probe failed")
    version_text = version_check.stdout.strip()
    if version_text != f"codex-cli {plan.get('host_proof_codex_version')}":
        raise ValueError("fresh worker Codex version does not match the host proof")
    completed = subprocess.run(
        [str(item) for item in plan["argv"]],  # type: ignore[index]
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"fresh Codex worker exited with code {completed.returncode}")
    session_id, final_text = _parse_exec_output(completed.stdout)
    metadata = verify_session_metadata(
        _session_path(session_id),
        expected_session_id=session_id,
        expected_model=str(plan["model"]),
        expected_effort=str(plan["reasoning_effort"]),
        expected_cwd=Path(str(plan["dossier_dir"])),
    )
    return {
        "schema": WORKER_SCHEMA,
        "status": "completed",
        "office_instance_kind": "fresh_codex_worker",
        "role": plan["role"],
        "model_route_id": plan["model_route_id"],
        "model": plan["model"],
        "reasoning_effort": plan["reasoning_effort"],
        "model_override_applied": True,
        "session_evidence": metadata,
        "final_text": final_text,
        "raw_stderr_persisted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-proof-json", type=Path, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--assignment", required=True)
    parser.add_argument("--task-focus", required=True)
    parser.add_argument("--complexity", choices=("low", "medium", "high", "critical"), required=True)
    parser.add_argument("--risk", choices=("low", "medium", "high", "critical"), required=True)
    parser.add_argument("--ambiguity", choices=("low", "medium", "high", "critical"), required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--sandbox", choices=sorted(ALLOWED_SANDBOXES), default="read-only")
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--native-codex-path", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    proof = json.loads(args.host_proof_json.read_text(encoding="utf-8"))
    plan = build_worker_plan(
        role=args.role,
        assignment=args.assignment,
        task_focus=args.task_focus,
        complexity=args.complexity,
        risk=args.risk,
        ambiguity=args.ambiguity,
        prompt=args.prompt,
        sandbox=args.sandbox,
        codex_executable=args.codex_executable,
        native_codex_path=args.native_codex_path,
        host_proof=proof,
    )
    payload = run_worker(plan, timeout_seconds=args.timeout_seconds) if args.run else plan
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
