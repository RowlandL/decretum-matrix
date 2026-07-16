"""Ensure the superCC zellij+squad visible court runtime.

superCC is one runtime implementation of the court-capability-router office
abstraction: ordinary ``super`` authority plus visible zellij panes, squad
identities, and a selected office client. Ordinary spawned subagents can carry
the same office identity through different proof gates; this script only checks
and launches the terminal-visible superCC substrate. The default client is
auto-selected from the current CLI surface and can be overridden globally or per
office.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
import textwrap
import time
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]

from court_file_lock import atomic_write_text
from court_dispatch_hierarchy import (
    DispatchHierarchyDecision,
    validate_dispatch_hierarchy,
)
from supercc_client_selection import (
    OFFICE_CLIENT_CHOICES,
    current_process_chain_signals,
    expand_office_selection,
    normalize_office_client_maps,
    office_client_command_for_role,
    office_client_extra_args,
    office_client_extra_args_for_role,
    office_client_for_role,
    office_client_prompt_mode_for_role,
    office_client_role_plan,
    resolve_office_client_args,
)
from supercc_office_state import (
    SUPERCC_HEALTH_SCHEMA,
    SUPERCC_STATE_SCHEMA,
    SUPERCC_STATE_SCHEMA_V1,
    append_turn_health as _append_turn_health,
    normalized_office_context,
    office_context_error,
    office_context_id,
    office_health_path,
    office_state_path,
    office_v1_state_error,
    office_v2_state_error,
    read_office_state,
    shiguan_runtime_path,
    supercc_runtime_lock_path,
    write_office_state as _write_office_state,
)


OFFICES: dict[str, dict[str, str]] = {
    "zhongshu": {
        "title": "AZS Zhongshu #0001",
        "office_zh": "中书省",
        "lineage": "AZS",
        "duty": "拟旨、考据、规划、拆解、验收标准；只向太子上奏，不直调六部。",
    },
    "menxia": {
        "title": "AMX Menxia #0001",
        "office_zh": "门下省",
        "lineage": "AMX",
        "duty": "封驳、风险/范围/隐私/成本复核、最终门下裁定；不直调六部。",
    },
    "shangshu": {
        "title": "ASS Shangshu #0001",
        "office_zh": "尚书省",
        "lineage": "ASS",
        "duty": "承太子回奏后统六部、发差遣、整合证据、回奏太子。",
    },
    "patrol-inspector": {
        "title": "AJC Jiancha #0001",
        "office_zh": "监察使",
        "lineage": "AJC",
        "duty": "监察 superCC 官署运行态、429/异常、显性窗口、非本轮会话残留与唤醒链；只显状态，不公开处置细节。",
    },
    "libu-hr": {
        "title": "BHR Libu-HR #0001",
        "office_zh": "吏部",
        "lineage": "BHR",
        "duty": "官籍、铨选、适任评分、招募建议和考课证据；向尚书省具奏。",
    },
    "hubu": {
        "title": "BHB Hubu #0001",
        "office_zh": "户部",
        "lineage": "BHB",
        "duty": "资源、路径、权限、依赖、版本、预算、服务和运行态核验；向尚书省具奏。",
    },
    "libu": {
        "title": "BLB Libu #0001",
        "office_zh": "礼部",
        "lineage": "BLB",
        "duty": "文书、报告契约、引用、说明和用户侧表述复核；向尚书省具奏。",
    },
    "bingbu": {
        "title": "BBB Bingbu #0001",
        "office_zh": "兵部",
        "lineage": "BBB",
        "duty": "战术、调度、并发、迁移和运行态事件处理；向尚书省具奏。",
    },
    "xingbu": {
        "title": "BXB Xingbu #0001",
        "office_zh": "刑部",
        "lineage": "BXB",
        "duty": "安全、隐私、破坏性操作、安装/打包风险和回滚/测试风险复核；向尚书省具奏。",
    },
    "gongbu": {
        "title": "BGB Gongbu #0001",
        "office_zh": "工部",
        "lineage": "BGB",
        "duty": "代码、脚本、构建、QA、部署和本地工具营造；向尚书省具奏。",
    },
    "shiguan": {
        "title": "ASH Shiguan #0001",
        "office_zh": "史馆",
        "lineage": "ASH",
        "duty": "三省共监、门下主审的实录、索引、记忆候选、考课与证据归档。",
    },
    "shiguan-hermes": {
        "title": "ASH Shiguan-Hermes #0001",
        "office_zh": "史馆",
        "lineage": "ASHH",
        "duty": "Hermes-compatible 史馆候补；仅在太子/门下省有界差遣下记录证据与兼容性说明。",
    },
    "zaochao": {
        "title": "AZC Zaochao #0001",
        "office_zh": "早朝",
        "lineage": "AZC",
        "duty": "向太子提供有界健康、状态、回顾与下一步简报；不批准或差遣执行。",
    },
}

TAIZI_PANE_TITLE = "S Taizi #0001"
TAIZI_OFFICE_ZH = "太子"
THREE_OFFICES = ("zhongshu", "menxia", "shangshu")
MINISTRY_OFFICES = ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
INSPECTION_OFFICES = ("patrol-inspector",)
SPECIAL_OFFICES = ("shiguan",)
SPECIAL_LIFECYCLE_OFFICES = (
    "shiguan",
    "shiguan-hermes",
    "zaochao",
    "patrol-inspector",
)
SPECIAL_LIFECYCLE_ACTIONS = {
    "shiguan": "archive_evidence_dispatch",
    "shiguan-hermes": "hermes_archive_evidence_dispatch",
    "zaochao": "briefing_dispatch",
    "patrol-inspector": "bounded_diagnostic_dispatch",
}
SUPERCC_VISIBLE_CORE_OFFICES = THREE_OFFICES
ALL_VISIBLE_OFFICES = (*SUPERCC_VISIBLE_CORE_OFFICES, *MINISTRY_OFFICES, *SPECIAL_OFFICES)
AGENT_DOSSIER_ROLES = ("taizi", *ALL_VISIBLE_OFFICES, *INSPECTION_OFFICES, "shiguan-hermes", "zaochao")
STATUS_OFFICES = ("taizi", *ALL_VISIBLE_OFFICES)
NON_VISIBLE_DEFAULT_SILENT_OFFICES = (*MINISTRY_OFFICES, *SPECIAL_OFFICES)
CLOSEOUT_SILENCE_ROLES = tuple(role for role in STATUS_OFFICES if role not in INSPECTION_OFFICES)
CORE_IDS = ("taizi", *ALL_VISIBLE_OFFICES, *INSPECTION_OFFICES)
NO_SILENCE_ROLES = ("taizi", *THREE_OFFICES)
MONITOR_NO_SILENCE_ROLES = NO_SILENCE_ROLES
EXPECTED_IDLE_MODES = ("silent", "idle_receive", "idle_receive_after_closeout")
TEST_AGENT_PREFIXES = ("court-zs-", "court-mx-", "court-ss-", "court-gb-")
CANONICAL_DUPLICATE_RE = re.compile(r"^(" + "|".join(re.escape(role) for role in CORE_IDS) + r")-\d+$")
UUID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
SQUAD_TASK_ID_RE = re.compile(rf"(?:\[task\s+|\bCreated\s+task\s+)({UUID_PATTERN})(?:\]|\b)", re.IGNORECASE)
DEFAULT_TIMEOUT = 30
SUPERCC_SESSION_CAP = None
SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE = 20
SUPERCC_REQUEST_TOTAL_LIMIT_DEFAULT = 20
SUPERCC_REQUEST_INTERVAL_SECONDS = 60.0 / SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE
SUPERCC_CODEX_MODEL_REQUESTS_PER_START_ESTIMATE = 4
SUPERCC_OFFICE_SHOW_DELAY_DEFAULT_SECONDS = 1.0
SUPERCC_OFFICE_SHOW_DELAY_MAX_SECONDS = 5.0
SUPERCC_CODEX_START_JITTER_DEFAULT_SECONDS = 0.0
SUPERCC_CODEX_BATCH_SIZE_DEFAULT = 1
SUPERCC_CODEX_RETRY_ATTEMPTS_DEFAULT = 1
SUPERCC_CODEX_RETRY_BACKOFF_DEFAULT_SECONDS = 5.0
QUEUED_RATE_LIMIT_STATE = "queued_rate_limit"
SUPERCC_SESSION_PROBE_TIMEOUT_SECONDS = 1.0
SUPERCC_SESSION_SCAN_BUDGET_SECONDS = 5.0
SUPERCC_RATE_LIMIT_STRESS_SCRIPT = "stress_supercc_rate_limit.py"
SUPERCC_WATCHDOG_SCRIPT = "supercc_watchdog.py"
SUPERCC_DOSSIER_ROOT_NAME = "supercc-dossiers"
SUPERCC_DOSSIER_FILE_NAME = "AGENTS.md"
SUPERCC_ENTRY_SCHEMA = "court.supercc.entry_plan.v1"
SUPERCC_LIGHT_BOOTSTRAP_POLICY = (
    "all office transports use per-office AGENTS.md dossiers as the long standing "
    "mandate; prompts carry an explicit role plus profile/dossier/SKILL path/hash "
    "manifest, and the office must return a preload ack before running."
)
OFFICE_PRELOAD_ACK_SCHEMA = "court.office.preload_ack.v1"
OFFICE_VOICE_POLICY = (
    "Office voice: act autonomously only inside this office mandate; report "
    "upward through the direct superior; refer to the acting subject by "
    "office_zh/官署代称, not first person (`我`, `我会`, `我已经`, `I`) or a generic "
    "`assistant` label."
)
POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS = 1.0
PHYSICAL_ENTER_BYTE = "13"
NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND = "SUPERCC_SQUAD_RECEIVE_COMMAND"
SQUAD_NOTICE_BEFORE_NATIVE_ENTER = "SQUAD_NOTICE_BEFORE_NATIVE_ENTER"
SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER = "SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER"
NON_VISIBLE_MINISTRY_DISPATCH_CHANNEL = "SQUAD_STRUCTURED_TASK_WITH_AUDIT_MIRROR_NON_VISIBLE_MINISTRY"
NON_VISIBLE_SPECIAL_LIFECYCLE_DISPATCH_CHANNEL = "SQUAD_STRUCTURED_TASK_WITH_AUDIT_MIRROR_NON_VISIBLE_SPECIAL_LIFECYCLE"
SILENT_SUPERVISOR_POLICY = "routine superCC visible offices exclude 监察; legacy visible monitor startup is disabled and scripts/supercc_watchdog.py owns 429/close/silence supervision as silent JSON/JSONL evidence."
SUPERCC_VISIBLE_LAYOUT_POLICY = "terminal-visible superCC keeps the current 太子 pane as the left column; every other visible office opens in the right-side column. The first office launch uses zellij --direction right from 太子, then later office launches focus the latest right-column pane and use --direction down."
SIX_MINISTRY_STEP_PLAN_POLICY = "六部 execution is a 尚书省 bounded step plan: dispatch real 六部 agents with bounded context; open-agent count is not capped, but model-triggering launches/dispatches must obey <=20 requests/minute and any explicit total request budget."
CLOSEOUT_SILENCE_POLICY = "after superCC final 结诏, resolved agente enter idle_receive except explicit unfinished roles; expected silence is recorded in Shiguan for silent supervisor evidence without creating visible monitor panes."
SUPERCC_CLI_CONTEXT_DRIFT_GUARD = "Ignore older transcripts, memory notes, or bootstrap prompts that show bare squad commands, hand-written cd commands, manually converted workspace paths, or controller-side zellij typing; this role dossier and wrapper contract supersede them."
TURN_START_NATIVE_WAKE_POLICY = "turn-start writes a bounded native prompt into visible 三省 panes, then sends Enter, waits one second, and sends a second physical Enter; this prevents squad-only wake messages from being missed when interactive Codex panes are idle at the prompt."
SUPERCC_PHASE_CYCLING_POLICY = "superCC phase cycling is governed by request-rate budgets rather than a fixed open-agent cap: planning/intake may keep 太子+三省 active; execution may open multiple 六部 agents, while model-triggering starts/dispatches stay <=20/minute and within any explicit total budget."
INSPECTOR_WAKE_CC_POLICY = "Routine superCC does not send inspector CC. Direct-superior supervision plus supercc_watchdog.py owns wake/heartbeat/rate-limit evidence; legacy --enable-inspector is compatibility-only."
SUPERCC_SUPER_ENTRY_POLICY = "superCC super-entry resolves a source CLI automatically or from user-specified global/per-office mappings, then routes launch/check/turn-start through structured ensure_supercc_court actions instead of hand-written zellij or bare squad commands."
SUPERCC_REQUEST_LIMIT_POLICY = "superCC removes the fixed <=5 open-agent gate. Visible office presentation uses an independent 0-5 second office_show_delay with no first-office cooldown, while provider request pressure uses a separate <=20 model-triggering requests/minute queue. Any wait beyond five seconds must be reported as queued_rate_limit/provider backoff rather than presentation delay. Outer launcher retries default to one attempt; explicit retry backoff defaults to five seconds and may honor a longer provider Retry-After without changing office_show_delay."
RATE_LIMIT_WAKE_HIERARCHY = {
    "taizi": {
        "owner": "zhongshu",
        "action": "中书省 reports/reminds 太子 liveness or 429/stale symptoms; it does not substitute for 太子",
    },
    "three_departments": {
        "roles": THREE_OFFICES,
        "owner": "taizi",
        "action": "太子 wakes or re-dispatches stale/429 三省 panes",
    },
    "ministries": {
        "roles": MINISTRY_OFFICES,
        "owner": "shangshu",
        "action": "尚书省 requeue/stagger/backoff/wake/ENTER_DISPATCH redispatches 六部 by step plan, then integrates 六部回奏 upward",
    },
    "final_review": {
        "roles": ("menxia",),
        "owner": "menxia",
        "action": "门下省 blocks final Done when supervision, dispatch, or ministry evidence is missing or drifted",
    },
    "patrol_inspector": {
        "roles": INSPECTION_OFFICES,
        "owner": "taizi_or_three_departments",
        "action": "if 监察使 is enabled and self-abnormal/429, it is woken or restarted by 太子 or any 三省; if disabled, this branch is NOT_APPLICABLE",
    },
}
SUPERVISION_CHANNEL = {
    "taizi_to_three_departments": {
        "owner": "taizi",
        "watches": THREE_OFFICES,
        "action": "wake_or_redispatch_three_departments",
    },
    "zhongshu_to_taizi": {
        "owner": "zhongshu",
        "watches": ("taizi",),
        "action": "report_or_remind_taizi_liveness_without_substitution",
    },
    "shangshu_to_ministries": {
        "owner": "shangshu",
        "watches": MINISTRY_OFFICES,
        "action": "requeue_stagger_backoff_wake_redispatch_and_integrate_ministry_reports",
    },
    "menxia_final_review": {
        "owner": "menxia",
        "watches": ("taizi", *THREE_OFFICES, *MINISTRY_OFFICES),
        "action": "block_done_when_supervision_dispatch_or_evidence_is_missing",
    },
}
STANDING_PROFILE_VERSION = "2026-06-27.supercc-profile.v1"
PROFILE_REQUIRED_FIELDS = (
    "role_key",
    "office_zh",
    "direct_superior",
    "duty",
    "can_do",
    "cannot_do",
    "procedure",
    "authority_basis",
    "report_contract",
    "evidence_contract",
    "heartbeat_contract",
    "dispatch_channel_policy",
    "release_policy",
    "profile_version",
    "profile_hash",
    "preload_contract_version",
    "dispatch_selection_policy",
    "capacity_admission_policy",
    "runtime_visibility_policy",
    "ordinary_parallel_policy",
    "startup_latency_contract",
    "codex_model_routing_policy",
    "claude_model_inheritance_policy",
    "hermes_model_inheritance_policy",
)
SQUAD_CLIENT_BY_OFFICE_CLIENT = {
    "codex": "codex",
    "claude": "claude",
    # squad has no native Hermes client enum yet. For Hermes-hosted superCC, omit
    # --client and rely on protocol-version evidence instead of mislabeling the
    # office as Codex/OpenCode.
    "hermescli": None,
    # Generic CLI tools are not a squad client enum. Preserve the runtime label
    # in evidence, but do not pass an invented --client value to squad.
    "cli": None,
}
HERMES_PROFILE_BY_ROLE = {
    "taizi": "taizi",
    "zhongshu": "zhongshu",
    "menxia": "menxia",
    "shangshu": "shangshu",
    "libu-hr": "libu-hr",
    "hubu": "hubu",
    "libu": "libu",
    "bingbu": "bingbu",
    "xingbu": "xingbu",
    "gongbu": "gongbu",
    # 监察使 is an inspection role, not Shiguan. Use the dedicated Jiancha
    # Hermes profile so the visible AJC Jiancha pane prompt/input shows jiancha
    # rather than shiguan/patrolinspector, while the squad role remains
    # patrol-inspector.
    "patrol-inspector": "jiancha",
    "shiguan": "shiguan",
}


def user_home() -> Path:
    configured = os.environ.get("USERPROFILE") if os.name == "nt" else os.environ.get("HOME")
    if configured:
        return Path(configured)
    return Path.home()


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def standing_profiles_dir() -> Path:
    return skill_root() / "agents" / "standing-officials"


def standing_profile_path(role: str) -> Path:
    return standing_profiles_dir() / f"{role}.toml"


def office_dossiers_root() -> Path:
    return skill_root() / "agents" / SUPERCC_DOSSIER_ROOT_NAME


def office_dossier_dir(role: str) -> Path:
    return office_dossiers_root() / role


def office_dossier_path(role: str) -> Path:
    return office_dossier_dir(role) / SUPERCC_DOSSIER_FILE_NAME


def skill_relative_path(path: Path) -> str:
    try:
        return path.relative_to(skill_root()).as_posix()
    except ValueError:
        return path.as_posix()


def supercc_squad_python_path() -> Path:
    return skill_root() / "scripts" / "supercc_squad.py"


def posix_command(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def powershell_arg(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def cmd_arg(value: str) -> str:
    text = str(value)
    if not text:
        return '""'
    if not any(char.isspace() or char in '^&|<>()%' for char in text):
        return text
    return '"' + text.replace('"', '""') + '"'


def supercc_squad_relative_commands(*args: str) -> dict[str, str]:
    arg_list = [str(arg) for arg in args]
    commands = {
        "posix": posix_command(["sh", "../../../scripts/supercc-squad.sh", *arg_list]),
        "powershell": "& " + " ".join([powershell_arg(r"..\..\..\scripts\supercc-squad.ps1"), *[powershell_arg(arg) for arg in arg_list]]),
        "cmd": " ".join([cmd_arg(r"..\..\..\scripts\supercc-squad.cmd"), *[cmd_arg(arg) for arg in arg_list]]),
        "windows": " ".join([cmd_arg("powershell.exe"), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", cmd_arg(r"..\..\..\scripts\supercc-squad.ps1"), *[cmd_arg(arg) for arg in arg_list]]),
        "python": posix_command(["python", "../../../scripts/supercc_squad.py", *arg_list]),
    }
    commands["native"] = commands["windows"] if os.name == "nt" else commands["posix"]
    return commands


def shell_contract_block(role: str, workspace: Path | None = None) -> str:
    receive = supercc_squad_relative_commands("receive", role, "--json")
    lines = [
        "Shell contract:",
        "- Primary rule: run the local superCC squad wrapper from the office dossier directory; do not hand-convert host paths.",
        f"- POSIX sh/bash/zsh: `{receive['posix']}`.",
        f"- PowerShell/pwsh: `{receive['powershell']}`.",
        f"- cmd.exe: `{receive['cmd']}`.",
        f"- Windows portable shell command: `{receive['windows']}`.",
        f"- Python fallback: `{receive['python']}`.",
        "- The wrapper resolves `squad` through PATH, environment overrides, and native host bridges when needed.",
        "- Use the same wrapper for other squad actions, for example `send`, `task ack`, and `task complete`.",
        "- Do not write shell-specific workspace paths into commands unless the wrapper reports that it cannot resolve the host program.",
        "- Never run bare squad commands directly from the task workspace; all receive/send/task traffic goes through the wrapper contract.",
        f"- {SUPERCC_CLI_CONTEXT_DRIFT_GUARD}",
        "- Controller/main panes must use `ensure_supercc_court.py --turn-start` or `--enter-dispatch` for native zellij delivery; hand-typed zellij dispatch without structured task and squad mirror evidence is invalid.",
    ]
    if workspace is not None:
        lines.append("- The task workspace is launcher-provided separately; it is not part of the receive command.")
    return "\n".join(lines)


def runtime_process_cwd_for_client(office_client: str, role: str, workspace: Path) -> Path:
    return office_dossier_dir(role)


def claude_project_key(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    text = str(resolved).replace("\\", "/")
    return text.rstrip("/") if len(text) > 3 else text


def default_claude_project_state() -> dict[str, Any]:
    return {
        "allowedTools": [],
        "mcpContextUris": [],
        "mcpServers": {},
        "enabledMcpjsonServers": [],
        "disabledMcpjsonServers": [],
        "hasTrustDialogAccepted": True,
        "projectOnboardingSeenCount": 0,
        "hasClaudeMdExternalIncludesApproved": False,
        "hasClaudeMdExternalIncludesWarningShown": False,
        "exampleFiles": [],
        "hasCompletedProjectOnboarding": True,
    }


def ensure_claude_project_trust(paths: list[Path], *, dry_run: bool = False) -> dict[str, Any]:
    config_path = Path.home() / ".claude.json"
    unique_keys: list[str] = []
    for path in paths:
        key = claude_project_key(path)
        if key not in unique_keys:
            unique_keys.append(key)
    if not unique_keys:
        return {"ok": True, "config_path": str(config_path), "trusted_project_keys": [], "changed": []}

    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "config_path": str(config_path), "reason": f"cannot_read_claude_json: {exc}"}
    else:
        data = {}
    if not isinstance(data, dict):
        return {"ok": False, "config_path": str(config_path), "reason": "claude_json_root_not_object"}
    projects = data.setdefault("projects", {})
    if not isinstance(projects, dict):
        return {"ok": False, "config_path": str(config_path), "reason": "claude_projects_not_object"}

    changed: list[str] = []
    for key in unique_keys:
        existing = projects.get(key)
        if not isinstance(existing, dict):
            existing = default_claude_project_state()
            changed.append(key)
        for field, value in default_claude_project_state().items():
            if field not in existing:
                existing[field] = value
                changed.append(key)
        if existing.get("hasTrustDialogAccepted") is not True:
            existing["hasTrustDialogAccepted"] = True
            changed.append(key)
        if existing.get("hasCompletedProjectOnboarding") is not True:
            existing["hasCompletedProjectOnboarding"] = True
            changed.append(key)
        projects[key] = existing

    changed = sorted(set(changed))
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "config_path": str(config_path),
            "trusted_project_keys": unique_keys,
            "would_change": changed,
        }
    if changed:
        try:
            config_path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "config_path": str(config_path), "reason": f"cannot_write_claude_json: {exc}"}
    return {
        "ok": True,
        "config_path": str(config_path),
        "trusted_project_keys": unique_keys,
        "changed": changed,
    }


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def read_toml(path: Path) -> dict[str, Any]:
    if tomllib is None or not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def profile_metadata(role: str) -> dict[str, Any]:
    path = standing_profile_path(role)
    parsed = read_toml(path)
    profile = parsed.get("profile", {}) if isinstance(parsed.get("profile", {}), dict) else {}
    missing = [field for field in PROFILE_REQUIRED_FIELDS if not str(profile.get(field, "")).strip()]
    return {
        "office_profile_loaded": bool(profile) and not missing,
        "profile_source": str(path),
        "profile_hash": sha256_file(path),
        "profile_version": profile.get("profile_version") or STANDING_PROFILE_VERSION,
        "profile_fields": profile,
        "profile_missing_fields": missing,
    }


def compact_profile_value(value: Any, limit: int | None = None) -> str:
    if isinstance(value, (list, tuple)):
        text = "; ".join(str(item) for item in value)
    else:
        text = str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    if limit is not None and len(text) > limit:
        return text[:limit].rstrip()
    return text


def profile_prompt_block(role: str) -> str:
    meta = profile_metadata(role)
    profile = meta.get("profile_fields", {})
    lines = [
        "Office profile:",
        f"- profile_source: {skill_relative_path(Path(str(meta['profile_source'])))}",
        f"- profile_hash: {meta.get('profile_hash') or 'missing'}",
        f"- profile_version: {meta.get('profile_version')}",
        f"- office_profile_loaded: {meta.get('office_profile_loaded')}",
    ]
    for key in (
        "role_key",
        "office_zh",
        "direct_superior",
        "can_do",
        "cannot_do",
        "procedure",
        "report_contract",
        "evidence_contract",
        "heartbeat_contract",
        "dispatch_channel_policy",
        "release_policy",
        "preload_contract_version",
        "dispatch_selection_policy",
        "capacity_admission_policy",
        "runtime_visibility_policy",
        "ordinary_parallel_policy",
        "startup_latency_contract",
        "codex_model_routing_policy",
        "claude_model_inheritance_policy",
        "hermes_model_inheritance_policy",
    ):
        if key in profile:
            lines.append(f"- {key}: {compact_profile_value(profile[key])}")
    if meta.get("profile_missing_fields"):
        lines.append(f"- profile_missing_fields: {', '.join(meta['profile_missing_fields'])}")
    return "\n".join(lines)


def office_display_info(role: str) -> dict[str, str]:
    profile = profile_metadata(role).get("profile_fields", {})
    if role in OFFICES:
        return dict(OFFICES[role])
    if role == "taizi":
        return {
            "title": TAIZI_PANE_TITLE,
            "office_zh": str(profile.get("office_zh") or TAIZI_OFFICE_ZH),
            "lineage": "S",
            "duty": str(profile.get("duty") or "Receive user decrees, relay court reports, and issue user-facing memorials."),
        }
    return {
        "title": "NOT_APPLICABLE",
        "office_zh": str(profile.get("office_zh") or role),
        "lineage": role,
        "duty": str(profile.get("duty") or "Standing Codex custom agent profile."),
    }


def profile_manifest_block(role: str) -> str:
    meta = profile_metadata(role)
    dossier = office_dossier_path(role)
    dossier_hash = sha256_file(dossier)
    court_skill = skill_root() / "SKILL.md"
    return "\n".join(
        [
            "Mode-neutral office preload manifest:",
            f"- preload_contract_version: {OFFICE_PRELOAD_ACK_SCHEMA}",
            f"- dossier_path: {skill_relative_path(dossier)}",
            f"- dossier_hash: {dossier_hash or 'missing'}",
            f"- profile_source: {skill_relative_path(Path(str(meta['profile_source'])))}",
            f"- profile_hash: {meta.get('profile_hash') or 'missing'}",
            f"- profile_version: {meta.get('profile_version')}",
            f"- office_profile_loaded: {meta.get('office_profile_loaded')}",
            f"- court_skill_path: {skill_relative_path(court_skill)}",
            f"- court_skill_hash: {sha256_file(court_skill) or 'missing'}",
            "- preload_ack: required before status=running; report role_key, direct_superior, all three hashes, agent_dossier_loaded=YES, and loaded_skills including court-capability-router.",
            "- collaboration_task_path: `/root/*` is routing only and never proves office identity.",
            "- ordinary_codex_model_route: keep reserved V2 spawn metadata hidden for schema compatibility; record the task-aware recommendation, require route-id plus inheritance acknowledgement, and inherit the main thread model/effort unless a host-managed override path is proven compatible.",
            "- claude_model_boundary: no office-level model override; inherit the main Claude thread model.",
            "- hermes_model_boundary: no office-level model override in this phase; inherit the main Hermes profile model; detailed profile design is deferred.",
            f"- light_bootstrap_policy: {SUPERCC_LIGHT_BOOTSTRAP_POLICY}",
        ]
    )


def office_hierarchy_rules(role: str, ministry_mode: str = "silent") -> dict[str, str]:
    if role == "taizi":
        return {
            "superior": "用户",
            "superior_agent": "user",
            "report_rule": "Report only to the user-facing final channel; relay subordinate questions as 太子转问 rather than exposing raw office debate.",
            "hierarchy_rule": (
                "You receive the newest decree, convene 三省 when non-trivial, synthesize 太子回奏, "
                "and never let another office address the user directly. Under court.dispatch_hierarchy.v1, "
                "normal execution dispatch is only taizi -> zhongshu|menxia|shangshu; never dispatch a Six Ministry directly."
            ),
            "default_state_rule": "Default state: AWAKE_NO_SILENCE while a decree is open; after closeout enter idle_receive.",
        }
    if role in THREE_OFFICES:
        hierarchy_rule = (
            "六部/workshop creation is only a 尚书省差遣 after approved 太子回奏. Under court.dispatch_hierarchy.v1, "
            "尚书省 alone dispatches the Six Ministries; "
            "each ministry may then dispatch only its own bounded child office. Require direct_superior=尚书省, "
            "context/evidence/heartbeat/release metadata, and never refresh or attach 六部 creation to the Taizi/main pane/menu. "
            f"{SIX_MINISTRY_STEP_PLAN_POLICY}"
            if role == "shangshu"
            else "Under court.dispatch_hierarchy.v1, this Three Department reports to 太子 and never dispatches a Six Ministry; "
            "only 尚书省 may do so after approved 太子回奏."
        )
        return {
            "superior": "太子",
            "superior_agent": "taizi",
            "report_rule": "Report only to 太子 through squad unless 尚书省 has an approved execution dispatch.",
            "hierarchy_rule": hierarchy_rule,
            "default_state_rule": "Default state: AWAKE for deliberation, but do not perform implementation work without an approved gate.",
        }
    if role in MINISTRY_OFFICES:
        default_state_rule = (
            "Default state: AWAKE because 尚书省 has explicitly dispatched this ministry."
            if ministry_mode == "awake"
            else "Default state: SILENT. Stay idle and do not inspect files, run commands, or reply until 尚书省 sends an explicit dispatch/wake message."
        )
        return {
            "superior": "尚书省",
            "superior_agent": "shangshu",
            "report_rule": "Report only to 尚书省 through squad, and do not address 太子 or the user directly unless an emergency sealed memorial is required.",
            "hierarchy_rule": (
                "You are a temporary 六部 pane under 尚书省 for this decree; preserve evidence, "
                "obey the context packet, and release or idle after 结诏 unless the user separately approves standing duty. "
                "Under court.dispatch_hierarchy.v1, you may dispatch only your own bounded child office. That child uses "
                "court.child_office_profile.v1 with canonical_authority=false and reuses the existing "
                "court.semantic.dispatch_context_packet.v1 plus court.semantic.invariant_capsule.v1; it never creates a second semantic authority. "
                f"{SIX_MINISTRY_STEP_PLAN_POLICY}"
            ),
            "default_state_rule": default_state_rule,
        }
    if role in INSPECTION_OFFICES:
        return {
            "superior": "太子/三省",
            "superior_agent": "taizi",
            "report_rule": "Report only when explicitly assigned a bounded diagnostic; routine supervision is silent supercc_watchdog.py evidence, not a visible monitor pane.",
            "hierarchy_rule": (
                "You are the legacy-compatible 监察使 / 监察 agente diagnostic identity. Do not create or expect a visible monitor pane; "
                "when explicitly dispatched, review only provided zellij/squad/watchdog evidence and report exceptions upward. "
                "Recovery remains owned by 太子, 三省, 尚书省, or supercc_watchdog.py according to hierarchy. "
                "After final 结诏, expected_silenced_roles are normal and must not be reported as errors solely because they are idle_receive/silent."
            ),
            "default_state_rule": "Default state: SILENT_NOT_LAUNCHED. Run only as an explicit bounded diagnostic; do not perform implementation work or public narrative.",
        }
    if role == "zaochao":
        return {
            "superior": "太子",
            "superior_agent": "taizi",
            "report_rule": "Report health/status briefings to 太子; do not dispatch 六部 or approve execution.",
            "hierarchy_rule": "You prepare morning-court summaries and retrospectives from evidence; you are not a standing execution office.",
            "default_state_rule": "Default state: SILENT unless explicitly assigned a briefing or retrospective task.",
        }
    return {
        "superior": "太子/门下省",
        "superior_agent": "taizi",
        "report_rule": "Report Shiguan evidence to 太子, with 门下省 as primary reviewer for records and memory decisions.",
        "hierarchy_rule": "You record and index evidence; you do not approve durable memory, dispatch 六部, or command execution.",
        "default_state_rule": "Default state: SILENT_NON_VISIBLE until explicitly dispatched; when dispatched, record evidence and memory candidates without approving durable memory by yourself.",
    }


def office_user_address_rule(role: str) -> str:
    if role == "taizi":
        return (
            "As the user-facing liaison, address the user only for decree intake, clarification relay, "
            "太子回奏, final closeout, pause/block/cancel/handoff, and never expose raw office debate."
        )
    return "Do not address the user directly, and never present a 三权选择 UI from an office pane."


def office_clarify_rule(role: str) -> str:
    if role == "taizi":
        return "When authority or work scope is missing, relay one plain clarification question to the user as 太子转问."
    return "Do not call clarify for authority selection; missing work scope means idle_receive / wait for squad dispatch, not asking the user."


def office_no_assignment_rule(role: str) -> str:
    if role in NO_SILENCE_ROLES:
        return (
            "If no assignment is present, or only a turn-start/open-decree control note is present, send one compact "
            "`AWAKE_NO_SILENCE assignment=none` memorial upward when appropriate, then stay idle at the prompt. "
            "Do not poll in a loop, do not run broad inspection, and do not write user-facing prose."
        )
    if role in INSPECTION_OFFICES:
        return (
            "If no assignment is present, or only a turn-start/open-decree control note is present, remain "
            "`idle_receive`/silent. Do not send `AWAKE_NO_SILENCE`, poll in a loop, run broad inspection, "
            "wake/restart offices, or write user-facing prose."
        )
    if role in SPECIAL_OFFICES or role == "shiguan-hermes":
        return (
            "If no assignment is present, or only a turn-start/open-decree control note is present, remain "
            "non-visible/silent in `idle_receive`. Do not send `AWAKE_NO_SILENCE`, poll in a loop, run indexing, "
            "run memory bridge checks, or write user-facing prose."
        )
    return (
        "If no assignment is present, or only a turn-start/open-decree control note is present, remain silent in "
        "`idle_receive`. Do not send `AWAKE_NO_SILENCE`, poll in a loop, run broad inspection, or write user-facing prose."
    )


def office_dossier_text(role: str) -> str:
    office = office_display_info(role)
    rules = office_hierarchy_rules(role)
    profile = textwrap.indent(profile_prompt_block(role), "        ")
    shell_contract = textwrap.indent(shell_contract_block(role), "        ")
    return textwrap.dedent(
        f"""
        # Mode-neutral Office Dossier: {office['office_zh']} ({role})

        This per-office `{SUPERCC_DOSSIER_FILE_NAME}` is the long standing mandate for terminal-visible superCC panes and explicitly selected superCC carriers. Ordinary spawned offices use `agents/office-dossiers/<role>/AGENTS.md`, not this superCC dossier. A collaboration address such as `/root/{role}_wave` is only routing metadata; office identity exists only after profile/dossier/court-skill hashes match and preload ack passes.

        ## Identity

        - role: {role}
        - office_zh: {office['office_zh']}
        - canonical_pane_title: {office['title']}
        - lineage: {office['lineage']}
        - direct_superior: {rules['superior']}
        - preload_contract_version: {OFFICE_PRELOAD_ACK_SCHEMA}
        - preload_ack: first report must include preload_status=PASSED, role_key={role}, matching profile_hash/dossier_hash/court_skill_hash, agent_dossier_loaded=YES, and loaded_skills including decretum-matrix.
        - light_bootstrap_policy: {SUPERCC_LIGHT_BOOTSTRAP_POLICY}

        ## Standing Mandate

        - Duty: {office['duty']}
        - {rules['report_rule']}
        - {rules['default_state_rule']}
        - {office_user_address_rule(role)}
        - {OFFICE_VOICE_POLICY}
        - {office_clarify_rule(role)}
        - Do not expand scope, spawn descendants, install tools, expose services, spend money, handle secrets, or perform destructive work without an approved 太子回奏 and matching court gate.
        - Treat superCC as super authority plus zellij/squad visible display and the selected runtime client, not as a higher safety authority or a different court-office essence from ordinary spawned office agents.
        - Hierarchy parity: ordinary and superCC use the same validator, `validate_dispatch_hierarchy`, under `court.dispatch_hierarchy.v1`; transport evidence may add pane/squad/native-enter fields but may not reinterpret the decision.
        - {rules['hierarchy_rule']}
        - Design-task 六部 dispatch requires a complete but bounded context packet; exclude secrets, credentials, private vaults, unrelated logs, and unrelated projects.
        - {SUPERCC_VISIBLE_LAYOUT_POLICY}
        - {SILENT_SUPERVISOR_POLICY}
        - {SUPERCC_CLI_CONTEXT_DRIFT_GUARD}

        ## Shell Contract

{shell_contract}

        ## Fast Dispatch Protocol

        1. Before duty work, load this dossier, the referenced standing profile, and Decretum Matrix `SKILL.md`; return the required preload ack. Do not claim running from task_name or `/root/*` alone.
        2. Your squad identity has already been joined by the launcher. Do not run squad join again unless Taizi explicitly sends REPAIR_IDENTITY.
        3. On wake, run exactly one non-blocking inbox check. Use the receive command from Shell Contract that matches your active shell and this role. Use `--wait` only when your direct superior explicitly asks you to wait.
        4. If a structured task exists, ack it first through the same wrapper, do only the bounded task, preserve evidence, then complete it through the same wrapper.
        5. If the assignment is an ENTER_DISPATCH packet, treat it as the current mandate; do not ask for authority again and do not reread global court references unless the packet is incomplete.
        6. Reply only upward through the same wrapper: `{supercc_squad_relative_commands('send', role, rules['superior_agent'], 'BRIEF_MEMORIAL ...')['posix']}` or the equivalent PowerShell/cmd wrapper form; ministries report to 尚书省, 三省 report to 太子.
        7. {office_no_assignment_rule(role)}

        ## Standing Profile

{profile}
        """
    ).strip() + "\n"


def ensure_office_dossier(role: str, *, dry_run: bool = False) -> dict[str, Any]:
    path = office_dossier_path(role)
    text = office_dossier_text(role)
    old_hash = sha256_file(path)
    new_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    changed = old_hash != new_hash
    if not dry_run and changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "role": role,
        "path": str(path),
        "hash": new_hash,
        "old_hash": old_hash,
        "changed": changed,
        "written": changed and not dry_run,
        "dry_run": dry_run,
    }


def write_agent_dossiers(args: argparse.Namespace) -> dict[str, Any]:
    roles = AGENT_DOSSIER_ROLES
    results = [ensure_office_dossier(role, dry_run=args.dry_run) for role in roles]
    return {
        "ok": all(item.get("ok") for item in results),
        "schema": "court.supercc.agent_dossiers.v1",
        "policy": SUPERCC_LIGHT_BOOTSTRAP_POLICY,
        "dossier_root": str(office_dossiers_root()),
        "dossier_file": SUPERCC_DOSSIER_FILE_NAME,
        "roles": list(roles),
        "changed_count": sum(1 for item in results if item.get("changed")),
        "written_count": sum(1 for item in results if item.get("written")),
        "dry_run": bool(args.dry_run),
        "dossiers": results,
    }


def with_office_dossier_state(role: str, state: dict[str, Any]) -> dict[str, Any]:
    if role not in OFFICES:
        return state
    dossier = office_dossier_path(role)
    enriched = dict(state)
    enriched["office_dossier_path"] = str(dossier)
    enriched["office_dossier_hash"] = sha256_file(dossier)
    enriched["light_bootstrap_policy"] = SUPERCC_LIGHT_BOOTSTRAP_POLICY
    return enriched


def tool_env() -> dict[str, str]:
    env = dict(os.environ)
    profile = os.environ.get("USERPROFILE") if os.name == "nt" else None
    if profile and not env.get("HOME"):
        env["HOME"] = profile
    tools_bin = env.get("COURT_TOOLS_BIN")
    current_path = env.get("PATH", "")
    if tools_bin and tools_bin.lower() not in current_path.lower():
        env["PATH"] = tools_bin + os.pathsep + current_path
    return env


def truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"...<truncated {len(text) - limit} chars>"


def zellij_command_args(*parts: str, session: str | None = None) -> list[str]:
    args = ["zellij"]
    if session:
        args.extend(["--session", session])
    args.extend(parts)
    return args


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    stdout_limit: int | None = 4000,
    stderr_limit: int | None = 4000,
) -> dict[str, Any]:
    invocation = resolved_invocation(args)
    try:
        completed = subprocess.run(
            invocation,
            cwd=str(cwd) if cwd else None,
            env=tool_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "args": args,
            "invocation": invocation,
            "stdout": stdout if stdout_limit is None else truncate(stdout, stdout_limit),
            "stderr": stderr if stderr_limit is None else truncate(stderr, stderr_limit),
            "stdout_truncated": stdout_limit is not None and len(stdout) > stdout_limit,
            "stderr_truncated": stderr_limit is not None and len(stderr) > stderr_limit,
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "returncode": None,
            "args": args,
            "invocation": invocation,
            "stdout": "",
            "stderr": f"not found: {exc}",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "args": args,
            "invocation": invocation,
            "stdout": truncate((exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""),
            "stderr": f"timeout after {timeout}s",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }


def run_command_with_input(
    args: list[str],
    input_text: str,
    *,
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    stdout_limit: int | None = 4000,
    stderr_limit: int | None = 4000,
) -> dict[str, Any]:
    invocation = resolved_invocation(args)
    try:
        completed = subprocess.run(
            invocation,
            input=input_text,
            cwd=str(cwd) if cwd else None,
            env=tool_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "args": args,
            "invocation": invocation,
            "stdout": stdout if stdout_limit is None else truncate(stdout, stdout_limit),
            "stderr": stderr if stderr_limit is None else truncate(stderr, stderr_limit),
            "stdout_truncated": stdout_limit is not None and len(stdout) > stdout_limit,
            "stderr_truncated": stderr_limit is not None and len(stderr) > stderr_limit,
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "returncode": None,
            "args": args,
            "invocation": invocation,
            "stdout": "",
            "stderr": f"not found: {exc}",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "args": args,
            "invocation": invocation,
            "stdout": truncate((exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""),
            "stderr": f"timeout after {timeout}s",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }


def native_pane_enter_sequence(
    workspace: Path,
    pane_id: str,
    text: str,
    *,
    dry_run: bool,
    zellij_session: str | None = None,
    payload_kind: str = "TEXT_PROMPT",
    squad_delivery_order: str = "UNSPECIFIED",
) -> dict[str, Any]:
    commands = [
        zellij_command_args("action", "write-chars", "-p", pane_id, text, session=zellij_session),
        zellij_command_args("action", "write", "-p", pane_id, PHYSICAL_ENTER_BYTE, session=zellij_session),
        ["sleep", f"{POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS:g}s"],
        zellij_command_args("action", "write", "-p", pane_id, PHYSICAL_ENTER_BYTE, session=zellij_session),
    ]
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "commands": commands,
            "native_enter_payload_kind": payload_kind,
            "squad_delivery_order": squad_delivery_order,
            "physical_enter_byte": PHYSICAL_ENTER_BYTE,
            "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
            "post_dispatch_physical_enter": "planned",
        }
    write_result = run_command(commands[0], cwd=workspace, timeout=10, stdout_limit=4000, stderr_limit=4000)
    enter_result = run_command(commands[1], cwd=workspace, timeout=10, stdout_limit=4000, stderr_limit=4000)
    time.sleep(max(0.0, POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS))
    post_enter_result = run_command(commands[3], cwd=workspace, timeout=10, stdout_limit=4000, stderr_limit=4000)
    return {
        "ok": bool(write_result.get("ok")) and bool(enter_result.get("ok")) and bool(post_enter_result.get("ok")),
        "write": write_result,
        "enter": enter_result,
        "native_enter_payload_kind": payload_kind,
        "squad_delivery_order": squad_delivery_order,
        "physical_enter_byte": PHYSICAL_ENTER_BYTE,
        "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
        "post_dispatch_physical_enter": post_enter_result,
        "commands": commands,
    }


def command_available(name: str) -> bool:
    return shutil.which(name, path=tool_env().get("PATH")) is not None


def gum_executable() -> str | None:
    found = shutil.which("gum", path=tool_env().get("PATH"))
    if found:
        return found
    tools_bin = os.environ.get("COURT_TOOLS_BIN")
    if tools_bin:
        fallback = Path(tools_bin) / ("gum.exe" if os.name == "nt" else "gum")
        if fallback.exists():
            return str(fallback)
    return None


def gum_status(workspace: Path) -> dict[str, Any]:
    executable = gum_executable()
    if not executable:
        return {"available": False, "path": None, "version": None}
    version = run_command([executable, "--version"], cwd=workspace, timeout=10, stdout_limit=1000, stderr_limit=1000)
    return {
        "available": bool(version.get("ok")),
        "path": executable,
        "version": version.get("stdout"),
        "version_result": version,
    }


def runtime_command_available(name: str) -> bool:
    if any(sep in name for sep in ("\\", "/")):
        return Path(name).exists()
    return command_available(name)


def supercc_bootstrap_needed(workspace: Path) -> bool:
    if not command_available("zellij") or not command_available("squad"):
        return True
    return not (workspace / ".squad").exists()


def maybe_bootstrap_supercc_dependencies(args: argparse.Namespace, workspace: Path) -> dict[str, Any]:
    if args.no_auto_install_deps:
        return {"ok": True, "skipped": True, "reason": "--no-auto-install-deps"}
    if getattr(args, "check_only", False):
        return {"ok": True, "skipped": True, "reason": "--check-only is read-only"}
    if getattr(args, "super_entry", None) in {"plan", "check", "check-only"}:
        return {"ok": True, "skipped": True, "reason": "--super-entry plan/check is read-only"}
    if getattr(args, "patrol", None) or getattr(args, "enter_dispatch", False):
        return {"ok": True, "skipped": True, "reason": "patrol/enter-dispatch never installs dependencies"}
    if args.dry_run:
        return {"ok": True, "skipped": True, "reason": "--dry-run"}
    if not supercc_bootstrap_needed(workspace):
        return {"ok": True, "skipped": True, "reason": "zellij/squad available and squad workspace initialized"}
    script = skill_root() / "scripts" / "ensure_portable_court_bootstrap.py"
    if not script.exists():
        return {"ok": False, "skipped": False, "reason": f"missing {script}"}
    command = [
        sys.executable,
        str(script),
        "--apply",
        "--supercc-deps-only",
        "--workspace",
        str(workspace),
        "--format",
        "json",
    ]
    if args.allow_unverified_release_asset:
        command.append("--allow-unverified-release-asset")
    result = run_command(command, cwd=skill_root(), timeout=600, stdout_limit=30000, stderr_limit=12000)
    parsed: dict[str, Any] | None = None
    if result.get("stdout"):
        try:
            parsed = json.loads(result["stdout"])
        except json.JSONDecodeError:
            parsed = None
    return {
        "ok": bool(result.get("ok")) and bool((parsed or {}).get("ok", result.get("ok"))),
        "skipped": False,
        "command": command[:3] + ["..."],
        "result": result,
        "payload": parsed,
    }


def resolved_invocation(args: list[str]) -> list[str]:
    if not args:
        return args
    command = args[0]
    if any(sep in command for sep in ("\\", "/")):
        resolved = command
    else:
        resolved = shutil.which(command, path=tool_env().get("PATH")) or command
    suffix = Path(resolved).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        cmd = "cmd.exe" if os.name == "nt" else shutil.which("cmd.exe")
        if cmd:
            return [cmd, "/d", "/c", resolved, *args[1:]]
        return [resolved, *args[1:]]
    if suffix == ".ps1":
        shell = (
            "powershell.exe"
            if os.name == "nt"
            else shutil.which("pwsh") or shutil.which("pwsh.exe") or shutil.which("powershell.exe")
        )
        if not shell:
            return [resolved, *args[1:]]
        return [
            shell,
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            resolved,
            *args[1:],
        ]
    return [resolved, *args[1:]]


def parse_json_lines(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"_parse_error": line})
    return rows


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def parse_zellij_panes(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in strip_ansi(text).splitlines():
        line = line.strip()
        if not line or line.startswith("PANE_ID"):
            continue
        match = re.match(r"^(\S+)\s+(\S+)(?:\s+(.*))?$", line)
        if not match:
            continue
        rows.append(
            {
                "pane_id": match.group(1),
                "type": match.group(2),
                "title": (match.group(3) or "").strip(),
            }
        )
    return rows


def parse_zellij_sessions(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in strip_ansi(text).splitlines():
        line = line.strip()
        if not line or line.startswith("Please specify"):
            continue
        name = line.split(maxsplit=1)[0]
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "exited": "EXITED" in line,
                "raw": line,
            }
        )
    return rows


def select_zellij_session(
    workspace: Path,
    sessions_result: dict[str, Any],
    explicit_session: str | None = None,
) -> dict[str, Any]:
    explicit = (explicit_session or "").strip()
    sessions_list = parse_zellij_sessions(sessions_result.get("stdout", ""))
    if explicit:
        return {"session": explicit, "source": "explicit_arg", "sessions_list": sessions_list, "pane_probes": []}
    env_session = (os.environ.get("ZELLIJ_SESSION_NAME") or "").strip()
    if env_session:
        return {"session": env_session, "source": "env", "sessions_list": sessions_list, "pane_probes": []}

    active_sessions = [row for row in sessions_list if not row.get("exited")]
    pane_probes: list[dict[str, Any]] = []
    scan_started = time.monotonic()
    probe_budget_exhausted = False
    for row in reversed(active_sessions):
        remaining_budget = SUPERCC_SESSION_SCAN_BUDGET_SECONDS - (time.monotonic() - scan_started)
        if remaining_budget <= 0:
            probe_budget_exhausted = True
            break
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        probe = run_command(
            zellij_command_args("action", "list-panes", session=name),
            cwd=workspace,
            timeout=max(1, int(min(SUPERCC_SESSION_PROBE_TIMEOUT_SECONDS, remaining_budget))),
            stdout_limit=50000,
            stderr_limit=4000,
        )
        panes = parse_zellij_panes(probe.get("stdout", "")) if probe.get("ok") else []
        has_taizi = any(pane.get("title") == TAIZI_PANE_TITLE for pane in panes)
        pane_probes.append(
            {
                "session": name,
                "ok": bool(probe.get("ok")),
                "pane_count": len(panes),
                "has_taizi_pane": has_taizi,
                "stderr": probe.get("stderr", ""),
            }
        )
        if has_taizi:
            return {
                "session": name,
                "source": "auto_taizi_pane",
                "sessions_list": sessions_list,
                "pane_probes": pane_probes,
                "probe_budget_exhausted": False,
                "unprobed_session_count": max(0, len(active_sessions) - len(pane_probes)),
            }

    if active_sessions:
        return {
            "session": str(active_sessions[-1].get("name")),
            "source": "auto_latest_active",
            "sessions_list": sessions_list,
            "pane_probes": pane_probes,
            "probe_budget_exhausted": probe_budget_exhausted,
            "unprobed_session_count": max(0, len(active_sessions) - len(pane_probes)),
        }
    return {
        "session": None,
        "source": "none",
        "sessions_list": sessions_list,
        "pane_probes": pane_probes,
        "probe_budget_exhausted": probe_budget_exhausted,
        "unprobed_session_count": 0,
    }


def check_zellij(workspace: Path, zellij_session: str | None = None) -> dict[str, Any]:
    version = run_command(["zellij", "--version"], cwd=workspace)
    sessions = run_command(["zellij", "list-sessions"], cwd=workspace)
    session_selection = select_zellij_session(workspace, sessions, zellij_session) if sessions.get("ok") else {
        "session": (zellij_session or os.environ.get("ZELLIJ_SESSION_NAME")),
        "source": "explicit_or_env_without_session_list",
        "sessions_list": [],
        "pane_probes": [],
    }
    selected_session = session_selection.get("session")
    panes = run_command(
        zellij_command_args("action", "list-panes", session=str(selected_session) if selected_session else None),
        cwd=workspace,
        timeout=max(1, int(SUPERCC_SESSION_PROBE_TIMEOUT_SECONDS)),
        stdout_limit=50000,
        stderr_limit=4000,
    )
    env_state = {
        "ZELLIJ": os.environ.get("ZELLIJ"),
        "ZELLIJ_SESSION_NAME": os.environ.get("ZELLIJ_SESSION_NAME"),
        "ZELLIJ_PANE_ID": os.environ.get("ZELLIJ_PANE_ID"),
    }
    session_prompt = "Please specify the session name" in "\n".join([panes.get("stdout", ""), panes.get("stderr", "")])
    panes_list = parse_zellij_panes(panes.get("stdout", "")) if panes["ok"] and not session_prompt else []
    inside = bool((selected_session or env_state["ZELLIJ_SESSION_NAME"] or env_state["ZELLIJ_PANE_ID"]) and panes["ok"] and panes_list)
    return {
        "available": command_available("zellij"),
        "inside": inside,
        "env": env_state,
        "selected_session": selected_session,
        "session_source": session_selection.get("source"),
        "sessions_list": session_selection.get("sessions_list", []),
        "session_pane_probes": session_selection.get("pane_probes", []),
        "session_probe_budget_exhausted": bool(session_selection.get("probe_budget_exhausted", False)),
        "unprobed_session_count": int(session_selection.get("unprobed_session_count", 0) or 0),
        "version": version,
        "panes": panes,
        "panes_list": panes_list,
        "panes_requires_explicit_session": session_prompt,
        "sessions": sessions,
    }


def check_squad(workspace: Path) -> dict[str, Any]:
    help_result = run_command(["squad", "help"], cwd=workspace)
    doctor = run_command(["squad", "doctor"], cwd=workspace)
    agents = run_command(["squad", "agents", "--all", "--json"], cwd=workspace, stdout_limit=200000)
    return {
        "available": command_available("squad"),
        "help": help_result,
        "doctor": doctor,
        "agents": agents,
        "agents_json": parse_json_lines(agents.get("stdout", "")) if agents["ok"] else [],
    }


def check_codex(workspace: Path) -> dict[str, Any]:
    return {
        "available": command_available("codex"),
        "version": run_command(["codex", "--version"], cwd=workspace),
        "help": run_command(["codex", "--help"], cwd=workspace),
    }


def check_claude(command: str, workspace: Path) -> dict[str, Any]:
    available = runtime_command_available(command)
    return {
        "available": available,
        "command": command,
        "version": run_command([command, "--version"], cwd=workspace) if available else None,
        "help": run_command([command, "--help"], cwd=workspace) if available else None,
    }


def probe_generic_cli(command: str, workspace: Path, extra_args: list[str], prompt_mode: str) -> dict[str, Any]:
    if not command:
        return {
            "ok": False,
            "command": "",
            "reason": "missing_command",
            "tool_resolution": "missing",
        }
    resolved = str(Path(command)) if any(sep in command for sep in ("\\", "/")) and Path(command).exists() else shutil.which(command)
    available = bool(resolved or runtime_command_available(command))
    probe: dict[str, Any] = {
        "ok": available,
        "command": command,
        "resolved_executable": resolved,
        "tool_resolution": "path_or_absolute" if resolved else "not_found",
        "extra_args": list(extra_args),
        "prompt_mode": prompt_mode,
        "known_from_probe": available,
        "version": None,
        "help": None,
        "recommended_prompt_delivery": prompt_mode,
    }
    if not available:
        probe["reason"] = "command_not_found"
        return probe
    version_attempts: list[dict[str, Any]] = []
    for version_args in (["--version"], ["version"], ["-v"]):
        result = run_command([command, *version_args], cwd=workspace, timeout=8, stdout_limit=3000, stderr_limit=3000)
        version_attempts.append({k: result.get(k) for k in ("ok", "returncode", "stdout", "stderr", "error", "args")})
        if result.get("ok") and ((result.get("stdout") or result.get("stderr"))):
            probe["version"] = version_attempts[-1]
            break
    help_attempts: list[dict[str, Any]] = []
    for help_args in (["--help"], ["help"], ["-h"]):
        result = run_command([command, *help_args], cwd=workspace, timeout=8, stdout_limit=5000, stderr_limit=3000)
        help_attempts.append({k: result.get(k) for k in ("ok", "returncode", "stdout", "stderr", "error", "args")})
        if result.get("ok") and ((result.get("stdout") or result.get("stderr"))):
            probe["help"] = help_attempts[-1]
            break
    probe["version_attempts"] = version_attempts
    probe["help_attempts"] = help_attempts
    probe["reason"] = None
    return probe


def check_office_client_values(
    office_client: str,
    hermescli_command: str,
    workspace: Path,
    *,
    claude_command: str = "claude",
    office_client_command: str | None = None,
    office_client_args: list[str] | None = None,
    office_client_prompt_mode: str = "argument",
    requested_office_client: str | None = None,
    selection_source: str | None = None,
    selection_signals: list[str] | None = None,
) -> dict[str, Any]:
    if office_client == "codex":
        return {
            "office_client": "codex",
            "requested_office_client": requested_office_client or office_client,
            "selection_source": selection_source,
            "selection_signals": selection_signals or [],
            "available": command_available("codex"),
            "command": "codex",
            "squad_client": SQUAD_CLIENT_BY_OFFICE_CLIENT["codex"],
            "generic_cli": False,
        }
    if office_client == "claude":
        available = runtime_command_available(claude_command)
        return {
            "office_client": "claude",
            "requested_office_client": requested_office_client or office_client,
            "selection_source": selection_source,
            "selection_signals": selection_signals or [],
            "available": available,
            "command": claude_command,
            "squad_client": SQUAD_CLIENT_BY_OFFICE_CLIENT["claude"],
            "generic_cli": False,
            "version": run_command([claude_command, "--version"], cwd=workspace) if available else None,
            "help": run_command([claude_command, "--help"], cwd=workspace) if available else None,
        }
    if office_client == "cli":
        command = office_client_command or ""
        available = bool(command and runtime_command_available(command))
        probe = probe_generic_cli(command, workspace, office_client_args or [], office_client_prompt_mode)
        return {
            "office_client": "cli",
            "requested_office_client": requested_office_client or office_client,
            "selection_source": selection_source,
            "selection_signals": selection_signals or [],
            "available": available,
            "command": command,
            "args": office_client_args or [],
            "prompt_mode": office_client_prompt_mode,
            "squad_client": SQUAD_CLIENT_BY_OFFICE_CLIENT["cli"],
            "generic_cli": True,
            "cli_probe": probe,
            "reason": None if available else "missing_or_unavailable_office_client_command",
        }
    command = hermescli_command
    return {
        "office_client": "hermescli",
        "requested_office_client": requested_office_client or office_client,
        "selection_source": selection_source,
        "selection_signals": selection_signals or [],
        "available": runtime_command_available(command),
        "command": command,
        "squad_client": SQUAD_CLIENT_BY_OFFICE_CLIENT["hermescli"],
        "generic_cli": False,
        "help": run_command([command, "--help"], cwd=workspace) if runtime_command_available(command) else None,
    }


def check_office_client(args: argparse.Namespace, workspace: Path) -> dict[str, Any]:
    return check_office_client_values(
        getattr(args, "office_client", "codex"),
        getattr(args, "hermescli_command", "hermescli"),
        workspace,
        claude_command=getattr(args, "claude_command", "claude"),
        office_client_command=getattr(args, "office_client_command", None),
        office_client_args=office_client_extra_args(args),
        office_client_prompt_mode=getattr(args, "office_client_prompt_mode", "argument"),
        requested_office_client=getattr(args, "requested_office_client", getattr(args, "office_client", None)),
        selection_source=getattr(args, "office_client_selection_source", None),
        selection_signals=getattr(args, "office_client_selection_signals", []),
    )


def check_office_client_for_role(args: argparse.Namespace, workspace: Path, role: str) -> dict[str, Any]:
    role_map = getattr(args, "office_client_map_resolved", {}) or {}
    mapped_client = role_map.get(role)
    client = office_client_for_role(args, role)
    return check_office_client_values(
        client,
        getattr(args, "hermescli_command", "hermescli"),
        workspace,
        claude_command=getattr(args, "claude_command", "claude"),
        office_client_command=office_client_command_for_role(args, role),
        office_client_args=office_client_extra_args_for_role(args, role),
        office_client_prompt_mode=office_client_prompt_mode_for_role(args, role),
        requested_office_client=mapped_client or getattr(args, "requested_office_client", getattr(args, "office_client", None)),
        selection_source="role_map" if mapped_client else getattr(args, "office_client_selection_source", None),
        selection_signals=[f"{role}={mapped_client}"] if mapped_client else getattr(args, "office_client_selection_signals", []),
    )


def normalize_squad_client_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "hermes": "hermescli",
        "hermes-cli": "hermescli",
        "claude-code": "claude",
        "generic": "cli",
        "generic-cli": "cli",
    }
    return aliases.get(raw, raw)


def office_identity_client_binding(
    check: dict[str, Any],
    role: str,
    selected_client: str,
) -> dict[str, Any]:
    """Compare the configured client with the active squad identity evidence.

    Executable availability only proves that a client *could* launch.  A live
    superCC truth gate must also prove that the canonical squad identity was
    joined by the same client family.
    """

    row = active_canonical_agent_row(check, role)
    expected = normalize_squad_client_type(selected_client)
    raw_actual = None
    if row:
        raw_actual = row.get("effective_client_type") or row.get("client_type") or row.get("client")
    actual = normalize_squad_client_type(raw_actual)
    ok = bool(row) and bool(actual) and actual == expected
    if not row:
        reason = "missing_active_canonical_squad_identity"
    elif not actual:
        reason = "active_squad_identity_missing_client_type"
    elif actual != expected:
        reason = "active_squad_identity_client_mismatch"
    else:
        reason = "ok"
    return {
        "ok": ok,
        "role": role,
        "selected_client": expected,
        "active_identity_client": actual or None,
        "active_identity_id": row.get("id") if row else None,
        "reason": reason,
        "policy": "selected_office_client_must_match_active_canonical_squad_identity",
    }


def check_office_clients_for_roles(
    args: argparse.Namespace,
    workspace: Path,
    roles: tuple[str, ...] | list[str],
    *,
    check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    per_role = {role: check_office_client_for_role(args, workspace, role) for role in roles}
    if check is not None:
        for role, result in per_role.items():
            result["active_identity_binding"] = office_identity_client_binding(
                check,
                role,
                str(result.get("office_client") or ""),
            )
    unavailable = [
        {
            "role": role,
            "office_client": result.get("office_client"),
            "command": result.get("command"),
            "reason": (
                (result.get("active_identity_binding") or {}).get("reason")
                if result.get("available") and check is not None
                else result.get("reason")
            ),
        }
        for role, result in per_role.items()
        if not result.get("available")
        or (check is not None and not (result.get("active_identity_binding") or {}).get("ok"))
    ]
    unique_clients: dict[str, list[str]] = {}
    for role, result in per_role.items():
        unique_clients.setdefault(str(result.get("office_client")), []).append(role)
    return {
        "available": not unavailable,
        "per_role": per_role,
        "unavailable_roles": unavailable,
        "unique_clients": unique_clients,
        "role_plan": office_client_role_plan(args, roles),
    }


def check_recursive_config(root: Path) -> dict[str, Any]:
    script = root / "scripts" / "ensure_court_agent_config.py"
    if not script.exists():
        return {"ok": False, "reason": f"missing {script}"}
    return run_command([sys.executable, str(script), "--check"], cwd=root)


def supercc_check(
    workspace: Path,
    *,
    office_client: str = "codex",
    hermescli_command: str = "hermescli",
    claude_command: str = "claude",
    office_client_command: str | None = None,
    office_client_args: list[str] | None = None,
    office_client_prompt_mode: str = "argument",
    zellij_session: str | None = None,
    office_client_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = skill_root()
    zellij = check_zellij(workspace, zellij_session=zellij_session)
    squad = check_squad(workspace)
    codex = check_codex(workspace)
    client = office_client_result or check_office_client_values(
        office_client,
        hermescli_command,
        workspace,
        claude_command=claude_command,
        office_client_command=office_client_command,
        office_client_args=office_client_args,
        office_client_prompt_mode=office_client_prompt_mode,
    )
    recursive_config = check_recursive_config(root)
    display_passed = (
        zellij["available"]
        and zellij["inside"]
        and squad["available"]
        and squad["help"]["ok"]
        and squad["doctor"]["ok"]
    )
    if client["office_client"] == "codex":
        client_passed = bool(codex["available"] and codex["version"]["ok"])
    elif client["office_client"] == "claude":
        client_passed = bool(client.get("available") and (client.get("version") or {}).get("ok"))
    else:
        client_passed = bool(client.get("available"))
    passed = display_passed and client_passed
    return {
        "supercc_env_gate": "PASSED" if passed else "runtime_degraded",
        "visible_display_gate": "PASSED" if display_passed else "runtime_degraded",
        "display_transport_gate": "PASSED" if display_passed else "runtime_degraded",
        "office_client_gate": "PASSED" if client_passed else "runtime_degraded",
        "passed": passed,
        "workspace": str(workspace),
        "skill_root": str(root),
        "zellij": zellij,
        "squad": squad,
        "codex": codex,
        "office_client": client,
        "recursive_config": recursive_config,
    }


def supercc_check_for_args(args: argparse.Namespace, workspace: Path) -> dict[str, Any]:
    office_client = check_office_client(args, workspace)
    return supercc_check(
        workspace,
        office_client=getattr(args, "office_client", "codex"),
        hermescli_command=getattr(args, "hermescli_command", "hermescli"),
        claude_command=getattr(args, "claude_command", "claude"),
        office_client_command=getattr(args, "office_client_command", None),
        office_client_args=office_client_extra_args(args),
        office_client_prompt_mode=getattr(args, "office_client_prompt_mode", "argument"),
        zellij_session=getattr(args, "zellij_session", None),
        office_client_result=office_client,
    )


def current_pane_id() -> str | None:
    pane = os.environ.get("ZELLIJ_PANE_ID")
    if not pane:
        return None
    if pane.startswith(("terminal_", "plugin_")):
        return pane
    return f"terminal_{pane}"


def parse_joined_agent(stdout: str, fallback: str) -> str:
    match = re.search(r"Joined as ([^\s]+)", stdout)
    if match:
        return match.group(1).rstrip(".")
    return fallback


def active_agent_ids(agents_json: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("id"))
        for row in agents_json
        if row.get("id") and row.get("status") != "archived"
    }


def active_agents_by_id(agents_json: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("id")): row
        for row in agents_json
        if row.get("id") and row.get("status") != "archived"
    }


def role_title(role: str) -> str:
    if role == "taizi":
        return TAIZI_PANE_TITLE
    return OFFICES[role]["title"]


def role_office_zh(role: str) -> str:
    if role == "taizi":
        return TAIZI_OFFICE_ZH
    return OFFICES[role]["office_zh"]


def is_expected_idle_mode(mode: Any) -> bool:
    text = str(mode or "").strip().lower()
    return text in EXPECTED_IDLE_MODES or text.startswith("silent")


def last_seen_age_seconds(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    value = row.get("last_seen") or row.get("joined_at")
    if value is None:
        return None
    try:
        return max(0.0, time.time() - float(value))
    except (TypeError, ValueError):
        return None


def simple_response_status(row: dict[str, Any] | None, *, inactive_age_seconds: float) -> dict[str, Any]:
    if not row:
        return {"ok": False, "reason": "missing_active_squad_identity"}
    age = last_seen_age_seconds(row)
    supports_json = bool(row.get("supports_json_receive"))
    supports_tasks = bool(row.get("supports_task_commands"))
    stale = age is None or age > inactive_age_seconds
    ok = supports_json and supports_tasks and not stale
    return {
        "ok": ok,
        "supports_json_receive": supports_json,
        "supports_task_commands": supports_tasks,
        "last_seen_age_seconds": None if age is None else round(age, 3),
        "inactive_age_seconds": inactive_age_seconds,
        "reason": "ok" if ok else "not_responsive_or_stale",
    }


def archive_agent(agent_id: str, workspace: Path, dry_run: bool) -> dict[str, Any]:
    args = ["squad", "leave", agent_id]
    if dry_run:
        return {"ok": True, "dry_run": True, "args": args}
    return run_command(args, cwd=workspace)


def maybe_archive_existing(
    agent_id: str,
    workspace: Path,
    agents_json: list[dict[str, Any]],
    *,
    reclaim_existing: bool,
    dry_run: bool,
) -> dict[str, Any] | None:
    if not reclaim_existing:
        return None
    if agent_id not in active_agent_ids(agents_json):
        return None
    return archive_agent(agent_id, workspace, dry_run)


def archive_test_agents(
    workspace: Path,
    agents_json: list[dict[str, Any]],
    *,
    dry_run: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in agents_json:
        agent_id = str(row.get("id", ""))
        if row.get("status") == "archived":
            continue
        if agent_id == "--help" or agent_id.startswith(TEST_AGENT_PREFIXES):
            results.append({"agent_id": agent_id, "result": archive_agent(agent_id, workspace, dry_run)})
    return results


def archive_duplicate_core_agents(
    workspace: Path,
    agents_json: list[dict[str, Any]],
    *,
    dry_run: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in agents_json:
        agent_id = str(row.get("id", ""))
        if row.get("status") == "archived":
            continue
        if CANONICAL_DUPLICATE_RE.match(agent_id):
            results.append({"agent_id": agent_id, "result": archive_agent(agent_id, workspace, dry_run)})
    return results


def pane_title_matches_role(title: str, role: str) -> bool:
    raw = title.strip().lower()
    expected = role_title(role).lower()
    if raw == expected or raw == role:
        return True
    # Interactive CLIs often overwrite the zellij title with a spinner prefix
    # plus the role name. Preserve strict duplicate counting while tolerating
    # that dynamic title drift.
    without_spinner = re.sub(r"^[^a-z0-9]+", "", raw)
    return without_spinner == role


def pane_title_is_canonical(title: str, role: str) -> bool:
    return title.strip().casefold() == role_title(role).strip().casefold()


def visible_office_panes(check: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    panes = check.get("zellij", {}).get("panes_list", [])
    result: dict[str, list[dict[str, str]]] = {}
    taizi_matches = [row for row in panes if row.get("title") == TAIZI_PANE_TITLE or pane_title_matches_role(str(row.get("title", "")), "taizi")]
    if taizi_matches:
        result["taizi"] = taizi_matches
    for role, office in OFFICES.items():
        matches = [row for row in panes if pane_title_matches_role(str(row.get("title", "")), role)]
        if matches:
            result[role] = matches
    return result


def select_unique_visible_pane(
    visible: dict[str, list[dict[str, str]]],
    role: str,
) -> dict[str, Any]:
    panes = visible.get(role, [])
    expected_title = role_title(role)
    if len(panes) == 1 and pane_title_is_canonical(str(panes[0].get("title", "")), role):
        pane = panes[0]
        return {
            "ok": True,
            "role": role,
            "pane": pane,
            "pane_id": pane.get("pane_id"),
            "expected_pane_title": expected_title,
            "visible_pane_count": 1,
            "policy": "unique_current_zellij_visible_pane_required",
        }
    if not panes:
        reason = "no_current_zellij_visible_pane"
    elif len(panes) > 1:
        reason = "duplicate_current_zellij_visible_panes"
    else:
        reason = "pane_title_drift"
    return {
        "ok": False,
        "role": role,
        "pane": None,
        "pane_id": None,
        "expected_pane_title": expected_title,
        "visible_pane_count": len(panes),
        "visible_panes": panes,
        "reason": reason,
        "policy": "unique_current_zellij_visible_pane_required",
    }


def current_zellij_session(check: dict[str, Any] | None = None) -> str | None:
    if check:
        selected = check.get("zellij", {}).get("selected_session")
        if selected:
            return str(selected)
        session = check.get("zellij", {}).get("env", {}).get("ZELLIJ_SESSION_NAME")
        if session:
            return str(session)
    return os.environ.get("ZELLIJ_SESSION_NAME")


def close_pane(pane_id: str, dry_run: bool, *, zellij_session: str | None = None) -> dict[str, Any]:
    args = zellij_command_args("action", "close-pane", "-p", pane_id, session=zellij_session)
    if dry_run:
        return {"ok": True, "dry_run": True, "args": args}
    return run_command(args, timeout=15)


def focus_pane(pane_id: str | None, dry_run: bool, *, zellij_session: str | None = None) -> dict[str, Any]:
    if not pane_id:
        return {"ok": False, "skipped": True, "reason": "missing_pane_id"}
    args = zellij_command_args("action", "focus-pane-id", pane_id, session=zellij_session)
    if dry_run:
        return {"ok": True, "dry_run": True, "args": args}
    return run_command(args, timeout=10)


def send_squad_notice(
    workspace: Path,
    sender: str,
    receiver: str,
    message: str,
    dry_run: bool,
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    args = ["squad", "send"]
    if task_id:
        args.extend(["--task-id", task_id])
    args.extend([sender, receiver, message])
    if dry_run:
        return {"ok": True, "dry_run": True, "args": args}
    return run_command(args, cwd=workspace, timeout=20)


def supercc_phase_for_roles(roles: tuple[str, ...] | list[str], *, sender: str = "") -> dict[str, Any]:
    role_set = set(roles)
    if role_set and role_set.issubset(set(THREE_OFFICES) | {"taizi", *INSPECTION_OFFICES}):
        phase = "planning_intake_phase"
        expected_active_model = "taizi+three_departments; patrol_inspector optional; requests<=20/min"
    elif role_set & set(MINISTRY_OFFICES):
        phase = "execution_ministry_phase"
        expected_active_model = "taizi+shangshu+selected_ministries; open-agent count uncapped; requests<=20/min"
    else:
        phase = "mixed_or_special_phase"
        expected_active_model = "must preserve request-rate budget<=20/min and explicit total budget when set"
    return {
        "supercc_phase_cycling_policy": SUPERCC_PHASE_CYCLING_POLICY,
        "supercc_request_limit_policy": SUPERCC_REQUEST_LIMIT_POLICY,
        "phase": phase,
        "roles": list(roles),
        "sender": sender,
        "expected_active_model": expected_active_model,
        "active_non_silent_window_cap": SUPERCC_SESSION_CAP,
        "request_rate_limit_per_minute": SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE,
        "phase_idle_expectation": "after 三省 returns, 三省 auto-idle; during ministry execution 中书省/门下省 remain idle unless re-woken by 太子",
    }


def inspector_wake_cc_message(
    *,
    action: str,
    sender: str,
    targets: tuple[str, ...] | list[str],
    reason: str,
    expected_mode: str,
    dispatch_uid: str | None = None,
    task_id: str | None = None,
) -> str:
    target_text = ",".join(targets)
    uid_text = dispatch_uid or "none"
    task_text = task_id or "none"
    return (
        f"[INSPECTOR_WAKE_CC] action={action}; sender={sender}; targets={target_text}; "
        f"expected_mode={expected_mode}; reason={reason}; dispatch_uid={uid_text}; task_id={task_text}; "
        "duty=verify_target_awake_received_or_heartbeat; if target not awakened, perform or escalate exactly one bounded re-wake through the superCC hierarchy; "
        "do not retry-loop; record wake_success|wake_failed evidence and preserve <=20/min request-rate gate."
    )


def send_inspector_wake_cc(
    workspace: Path,
    sender: str,
    targets: tuple[str, ...] | list[str],
    *,
    reason: str,
    expected_mode: str,
    dry_run: bool,
    dispatch_uid: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    message = inspector_wake_cc_message(
        action="wake_or_dispatch_observe",
        sender=sender,
        targets=targets,
        reason=reason,
        expected_mode=expected_mode,
        dispatch_uid=dispatch_uid,
        task_id=task_id,
    )
    return {
        "policy": INSPECTOR_WAKE_CC_POLICY,
        "target_role": "patrol-inspector",
        "observed_targets": list(targets),
        "expected_mode": expected_mode,
        "dispatch_uid": dispatch_uid,
        "task_id": task_id,
        "result": send_squad_notice(workspace, sender, "patrol-inspector", message, dry_run),
    }


def skipped_inspector_wake_cc(sender: str, targets: tuple[str, ...] | list[str], reason: str) -> dict[str, Any]:
    return {
        "ok": True,
        "skipped": True,
        "sender": sender,
        "targets": list(targets),
        "reason": reason,
        "policy": "routine superCC has no dedicated 监察 pane; direct superior preserves wake, heartbeat, and rate-limit evidence.",
    }


def inspector_enabled(args: argparse.Namespace) -> bool:
    return False


def maybe_send_inspector_wake_cc(
    args: argparse.Namespace,
    workspace: Path,
    sender: str,
    targets: tuple[str, ...] | list[str],
    *,
    reason: str,
    expected_mode: str,
    dispatch_uid: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    if not inspector_enabled(args):
        reason_text = "--skip-inspector" if getattr(args, "skip_inspector", False) else "default_hierarchical_supervision"
        return skipped_inspector_wake_cc(sender, targets, reason_text)
    return send_inspector_wake_cc(
        workspace,
        sender,
        targets,
        reason=reason,
        expected_mode=expected_mode,
        dry_run=args.dry_run,
        dispatch_uid=dispatch_uid,
        task_id=task_id,
    )


def parse_squad_task_id(text: str) -> str | None:
    match = SQUAD_TASK_ID_RE.search(text)
    return match.group(1) if match else None


def create_squad_task_assignment(
    workspace: Path,
    sender: str,
    receiver: str,
    *,
    title: str,
    body: str,
    dispatch_uid: str,
    dry_run: bool,
) -> dict[str, Any]:
    args = ["squad", "task", "create", sender, receiver, "--title", title, "--body", body]
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "command": args,
            "task_id": f"dry-run-{dispatch_uid}",
            "policy": "structured_task_required_for_office_execution",
        }
    result = run_command(args, cwd=workspace, timeout=20, stdout_limit=8000, stderr_limit=8000)
    task_id = parse_squad_task_id(f"{result.get('stdout', '')}\n{result.get('stderr', '')}")
    return {
        **result,
        "command": args,
        "task_id": task_id,
        "policy": "structured_task_required_for_office_execution",
        "task_id_parse_ok": bool(task_id),
    }


def active_canonical_agent_row(check: dict[str, Any], role: str) -> dict[str, Any] | None:
    return active_agents_by_id(check.get("squad", {}).get("agents_json", [])).get(role)


def active_rows_for_role(check: dict[str, Any], role: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in check.get("squad", {}).get("agents_json", []):
        if row.get("status") == "archived":
            continue
        if str(row.get("role", "")) == role:
            rows.append(row)
    return rows


def office_uniqueness_gate(
    check: dict[str, Any],
    visible: dict[str, list[dict[str, str]]],
    role: str,
    *,
    require_visible: bool = True,
) -> dict[str, Any]:
    role_rows = active_rows_for_role(check, role)
    canonical_row = active_canonical_agent_row(check, role)
    active_ids = [str(row.get("id", "")) for row in role_rows if row.get("id")]
    duplicate_identity_ids = [agent_id for agent_id in active_ids if agent_id != role]
    pane_selection = select_unique_visible_pane(visible, role)
    panes = visible.get(role, [])
    active_identity_ok = canonical_row is not None and len(role_rows) == 1 and active_ids == [role]
    if require_visible:
        current_session_pane_ok = bool(pane_selection.get("ok"))
    else:
        current_session_pane_ok = not panes or bool(pane_selection.get("ok"))
    ok = active_identity_ok and current_session_pane_ok
    reasons: list[str] = []
    if canonical_row is None:
        reasons.append("missing_active_canonical_squad_identity")
    if len(role_rows) > 1 or duplicate_identity_ids:
        reasons.append("duplicate_active_squad_identities_for_role")
    if require_visible and not panes:
        reasons.append("missing_current_zellij_pane_for_visible_role")
    if len(panes) > 1:
        reasons.append("duplicate_current_zellij_panes_for_role")
    if len(panes) == 1 and not pane_selection.get("ok"):
        reasons.append("current_zellij_pane_title_not_canonical")
    return {
        "ok": ok,
        "role": role,
        "policy": (
            "one_office_role_one_active_squad_identity_and_exactly_one_canonical_current_session_pane"
            if require_visible
            else "one_office_role_one_active_squad_identity_and_zero_or_one_canonical_current_session_pane"
        ),
        "visible_pane_required": require_visible,
        "active_identity_ok": active_identity_ok,
        "active_squad_ids_for_role": active_ids,
        "active_squad_rows_for_role": role_rows,
        "canonical_squad_identity": canonical_row,
        "duplicate_identity_ids": duplicate_identity_ids,
        "current_session_pane_ok": current_session_pane_ok,
        "visible_pane_count": len(panes),
        "visible_panes": panes,
        "visible_pane_selection": pane_selection,
        "pane_process_binding": role_pane_process_binding(check, visible, role),
        "reason": "ok" if ok else ",".join(reasons),
    }


def role_pane_process_binding(check: dict[str, Any], visible: dict[str, list[dict[str, str]]], role: str) -> dict[str, Any]:
    """Bind a court role to the current zellij pane and squad identity.

    Zellij's stable public evidence here is pane id/title/session. It does not
    expose a child OS PID through `list-panes`, so process evidence is explicit:
    when an OS PID cannot be obtained without unsafe host-specific probing, the
    binding is pane_id + canonical title + active squad id + profile hash.
    """
    pane_selection = select_unique_visible_pane(visible, role)
    row = active_canonical_agent_row(check, role)
    profile = profile_metadata(role)
    return {
        "role": role,
        "zellij_session": current_zellij_session(check),
        "expected_pane_title": role_title(role),
        "pane_id": pane_selection.get("pane_id"),
        "pane_selection": pane_selection,
        "active_squad_id": row.get("id") if row else None,
        "active_squad_role": row.get("role") if row else None,
        "profile_source": profile.get("profile_source"),
        "profile_hash": profile.get("profile_hash"),
        "profile_version": profile.get("profile_version"),
        "process_id": None,
        "process_id_evidence": "zellij list-panes does not expose child OS PID on this host; using current-session pane_id + canonical title + squad identity + profile hash binding",
        "binding_ok": bool(pane_selection.get("ok")) and row is not None and bool(profile.get("office_profile_loaded")),
    }


def write_office_state(
    workspace: Path,
    modes: dict[str, dict[str, Any]],
    *,
    zellij_session: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    return _write_office_state(
        workspace,
        modes,
        zellij_session=zellij_session,
        dry_run=dry_run,
        state_enricher=with_office_dossier_state,
        atomic_writer=atomic_write_text,
    )


def append_turn_health(payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    return _append_turn_health(payload, dry_run, atomic_writer=atomic_write_text)


def compact_command(parts: list[str] | tuple[str, ...]) -> list[str]:
    compact: list[str] = []
    omit_next = False
    for part in parts:
        if omit_next:
            compact.append("<encoded-powershell-omitted>")
            omit_next = False
            continue
        compact.append(str(part))
        if part == "-EncodedCommand":
            omit_next = True
    return compact


def join_agent(agent_id: str, role: str, workspace: Path, dry_run: bool, *, office_client: str = "codex") -> dict[str, Any]:
    squad_client = SQUAD_CLIENT_BY_OFFICE_CLIENT.get(office_client)
    args = [
        "squad",
        "join",
        agent_id,
        "--role",
        role,
    ]
    if squad_client:
        args.extend(["--client", squad_client])
    args.extend(["--protocol-version", "2"])
    if dry_run:
        return {"ok": True, "dry_run": True, "args": args, "actual_id": agent_id, "office_client": office_client}
    result = run_command(args, cwd=workspace)
    result["actual_id"] = parse_joined_agent(result.get("stdout", ""), agent_id)
    result["office_client"] = office_client
    return result


def rename_taizi_pane(
    dry_run: bool,
    *,
    pane_id: str | None = None,
    zellij_session: str | None = None,
) -> dict[str, Any]:
    pane_id = pane_id or current_pane_id()
    args = zellij_command_args("action", "rename-pane", session=zellij_session)
    if pane_id:
        args.extend(["-p", pane_id])
    args.append(TAIZI_PANE_TITLE)
    if dry_run:
        return {"ok": True, "dry_run": True, "args": args}
    return run_command(args)


def ps_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def ps_array_literal(values: list[str]) -> str:
    return "@(" + ",".join(ps_literal(value) for value in values) + ")"


def encode_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def office_prompt(
    agent_id: str,
    role: str,
    workspace: Path,
    court_code: str | None,
    *,
    office_client: str = "codex",
    ministry_mode: str = "silent",
) -> str:
    office = OFFICES[role]
    code_line = f"court_code={court_code}" if court_code else "court_code=pending"
    rules = office_hierarchy_rules(role, ministry_mode)
    superior = rules["superior"]
    superior_agent = rules["superior_agent"]
    hierarchy_rule = rules["hierarchy_rule"]
    default_state_rule = rules["default_state_rule"]
    manifest_block = textwrap.indent(profile_manifest_block(role), "        ")
    shell_contract = textwrap.indent(shell_contract_block(role, workspace), "        ")
    return textwrap.dedent(
        f"""
        superCC office bootstrap: {office['office_zh']} ({role})
        Authority already selected by 太子: superCC. Do not show a 三权 selector and do not run squad join unless REPAIR_IDENTITY is sent.
        {code_line}
        task_workspace_env=SUPERCC_TASK_WORKSPACE
        office_runtime_cwd=role_dossier_directory
        squad_id={agent_id}
        runtime_client={office_client}
        direct_superior={superior}
        default_state={default_state_rule}
        layout_policy={SUPERCC_VISIBLE_LAYOUT_POLICY}

{manifest_block}

{shell_contract}

        Fast path:
        1. If the auto-loaded {SUPERCC_DOSSIER_FILE_NAME} is absent from context, read dossier_path once; otherwise rely on it.
        2. Run one non-blocking receive through the local superCC squad wrapper from Shell contract. Do not hand-convert workspace paths, do not use the task workspace as receive cwd, and ignore stale examples that use bare squad commands.
        3. If a task is present, ack/execute/complete it with concise evidence. If an ENTER_DISPATCH packet is present, act on it immediately inside scope.
        4. Report only upward through the same wrapper: send {agent_id} {superior_agent} BRIEF_MEMORIAL ...
        5. If no assignment is present, stay idle at the prompt; do not poll, browse, inspect broadly, or address the user.
        Drift guard: {SUPERCC_CLI_CONTEXT_DRIFT_GUARD}
        Hierarchy: {hierarchy_rule}
        """
    ).strip()


def build_office_launch_command(
    role: str,
    workspace: Path,
    *,
    court_code: str | None,
    office_client: str,
    hermescli_command: str,
    claude_command: str,
    office_client_command: str | None,
    office_client_args: list[str],
    office_client_prompt_mode: str,
    zellij_session: str | None,
    ministry_mode: str,
    dangerous_yolo: bool,
    codex_start_delay: float,
    codex_retry_attempts: int,
    codex_retry_backoff_base: float,
    layout_direction: str,
) -> list[str]:
    if layout_direction not in {"right", "down"}:
        raise ValueError(f"unsupported zellij layout direction: {layout_direction}")
    prompt = office_prompt(role, role, workspace, court_code, office_client=office_client, ministry_mode=ministry_mode)
    office_runtime_cwd = office_dossier_dir(role)
    runtime_process_cwd = runtime_process_cwd_for_client(office_client, role, workspace)
    squad_client = SQUAD_CLIENT_BY_OFFICE_CLIENT.get(office_client)
    runtime_label = {
        "codex": "Codex",
        "claude": "Claude Code",
        "hermescli": "Hermes CLI",
        "cli": f"Generic CLI ({Path(office_client_command or 'cli').name})",
    }.get(office_client, office_client)
    if office_client == "hermescli":
        hermes_profile = HERMES_PROFILE_BY_ROLE.get(role, role)
        runtime_args = [
            hermescli_command,
            "--profile",
            hermes_profile,
            "chat",
            "--skills",
            "court-capability-router",
            "--max-turns",
            "90",
            "--yolo",
            "--cli",
        ]
    elif office_client == "claude":
        runtime_args = [
            claude_command,
            "--dangerously-skip-permissions",
            "--permission-mode",
            "bypassPermissions",
            "--add-dir",
            str(workspace),
            "--add-dir",
            str(office_runtime_cwd),
            "--name",
            OFFICES[role]["title"],
            "--append-system-prompt",
            (
                "You are a terminal-visible superCC office launched by "
                "court-capability-router. Preserve the office role, direct "
                "superior, wrapper receive loop, and concise upward memorial "
                "contract from the initial prompt."
            ),
            "--",
        ]
    elif office_client == "cli":
        runtime_args = [
            office_client_command or "missing-office-client-command",
            *office_client_args,
        ]
    else:
        runtime_args = [
            "codex",
            "--no-alt-screen",
            "-C",
            str(office_runtime_cwd),
            "--search",
        ]
        if dangerous_yolo:
            runtime_args.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            runtime_args.extend(["--sandbox", "danger-full-access", "--ask-for-approval", "never"])
        runtime_args.append("--")

    squad_join_args = ["join", role, "--role", role]
    if squad_client:
        squad_join_args.extend(["--client", squad_client])
    squad_join_args.extend(["--protocol-version", "2"])
    start_delay = max(0, int(round(bounded_office_show_delay(codex_start_delay))))
    retry_attempts = max(1, int(codex_retry_attempts))
    backoff_base = max(0, int(round(provider_retry_backoff_seconds(codex_retry_backoff_base))))
    prompt_mode = office_client_prompt_mode if office_client == "cli" else ("stdin" if office_client == "hermescli" else "argument")

    if os.name != "nt":
        runtime_command = " ".join(shlex.quote(str(part)) for part in runtime_args)
        squad_join_command = " ".join(
            shlex.quote(str(part))
            for part in [str(skill_root() / "scripts" / "supercc-squad.sh"), *squad_join_args]
        )
        prompt_delimiter = "SUPERCC_PROMPT_EOF"
        while prompt_delimiter in prompt:
            prompt_delimiter += "_X"
        posix_script = "\n".join(
            [
                "set +e",
                "if [ -n \"${COURT_TOOLS_BIN:-}\" ]; then PATH=\"$COURT_TOOLS_BIN:$PATH\"; export PATH; fi",
                f"actual_workspace={shlex.quote(str(workspace))}",
                f"office_dossier={shlex.quote(str(office_dossier_path(role)))}",
                f"runtime_process_cwd={shlex.quote(str(runtime_process_cwd))}",
                "export SUPERCC_TASK_WORKSPACE=\"$actual_workspace\"",
                f"export SUPERCC_OFFICE_DOSSIER={shlex.quote(str(office_runtime_cwd))}",
                f"export SUPERCC_SKILL_ROOT={shlex.quote(str(skill_root()))}",
                'printf "%s\\n" "[superCC] actual task workspace: $actual_workspace"',
                'printf "%s\\n" "[superCC] office dossier: $office_dossier"',
                'printf "%s\\n" "[superCC] runtime process cwd: $runtime_process_cwd"',
                f"cd {shlex.quote(str(runtime_process_cwd))} || exit 1",
                f"({{ sleep {start_delay + 3}; {squad_join_command}; }}) >/dev/null 2>&1 &",
                f"PROMPT=$(cat <<'{prompt_delimiter}'",
                prompt,
                prompt_delimiter,
                ")",
                f"startup_delay={start_delay}",
                f"max_attempts={retry_attempts}",
                f"backoff_base={backoff_base}",
                f"prompt_mode={shlex.quote(prompt_mode)}",
                f"runtime_label={shlex.quote(runtime_label)}",
                "if [ \"$startup_delay\" -gt 0 ]; then",
                '  printf "%s\\n" "[superCC] async $runtime_label startup stagger: waiting $startup_delay seconds"',
                "  sleep \"$startup_delay\"",
                "fi",
                "exit_code=0",
                "attempt=1",
                "while [ \"$attempt\" -le \"$max_attempts\" ]; do",
                '  printf "%s\\n" "[superCC] starting $runtime_label attempt $attempt/$max_attempts"',
                "  if [ \"$prompt_mode\" = stdin ]; then",
                f"    printf '%s' \"$PROMPT\" | {runtime_command}",
                "  else",
                f"    {runtime_command} \"$PROMPT\"",
                "  fi",
                "  exit_code=$?",
                "  [ \"$exit_code\" -eq 0 ] && break",
                "  if [ \"$attempt\" -lt \"$max_attempts\" ]; then",
                "    retry_delay=$backoff_base",
                "    retry_step=1",
                "    while [ \"$retry_step\" -lt \"$attempt\" ]; do retry_delay=$(( retry_delay * 2 )); retry_step=$(( retry_step + 1 )); done",
                "    [ \"$retry_delay\" -gt 600 ] && retry_delay=600",
                '    printf "%s\\n" "[ATTN] state=queued_provider_retry runtime=$runtime_label exit=$exit_code backoff_seconds=$retry_delay"',
                "    sleep \"$retry_delay\"",
                "  fi",
                "  attempt=$(( attempt + 1 ))",
                "done",
                "if [ \"$exit_code\" -ne 0 ]; then",
                '  printf "%s\\n" "[ATTN] $runtime_label exited with code $exit_code after $max_attempts attempts"',
                "fi",
                "exit \"$exit_code\"",
            ]
        )
        return zellij_command_args(
            "run",
            "--cwd",
            str(runtime_process_cwd),
            "--name",
            OFFICES[role]["title"],
            "--direction",
            layout_direction,
            "--",
            "sh",
            "-lc",
            posix_script,
            session=zellij_session,
        )

    runtime_args_ps = ps_array_literal(runtime_args)
    squad_join_args_ps = ps_array_literal(squad_join_args)
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Continue'",
            "if (-not $env:HOME -and $env:USERPROFILE) { $env:HOME = $env:USERPROFILE }",
            "if ($env:COURT_TOOLS_BIN -and $env:Path -notlike ('*' + $env:COURT_TOOLS_BIN + '*')) { $env:Path = $env:COURT_TOOLS_BIN + [IO.Path]::PathSeparator + $env:Path }",
            f"$actualWorkspace = {ps_literal(workspace)}",
            f"$officeRuntimeCwd = {ps_literal(office_runtime_cwd)}",
            f"$runtimeProcessCwd = {ps_literal(runtime_process_cwd)}",
            "$env:SUPERCC_TASK_WORKSPACE = $actualWorkspace",
            "$env:SUPERCC_OFFICE_DOSSIER = $officeRuntimeCwd",
            f"$env:SUPERCC_SKILL_ROOT = {ps_literal(skill_root())}",
            "Set-Location -LiteralPath $runtimeProcessCwd",
            f"$officeDossier = {ps_literal(office_dossier_path(role))}",
            f"$squadWrapper = {ps_literal(skill_root() / 'scripts' / 'supercc-squad.ps1')}",
            f"$squadJoinArgs = {squad_join_args_ps}",
            "$prompt = @'",
            prompt,
            "'@",
            f"$runtimeArgs = {runtime_args_ps}",
            f"$startupDelay = {start_delay}",
            f"$maxAttempts = {retry_attempts}",
            f"$backoffBase = {backoff_base}",
            f"$runtimeLabel = {ps_literal(runtime_label)}",
            f"$promptMode = {ps_literal(prompt_mode)}",
            'Write-Host "[superCC] actual task workspace: $actualWorkspace"',
            'Write-Host "[superCC] office dossier: $officeDossier"',
            'Write-Host "[superCC] runtime process cwd: $runtimeProcessCwd"',
            "$exe = $runtimeArgs[0]",
            "$rest = $runtimeArgs[1..($runtimeArgs.Length - 1)]",
            # Start squad join in background after office startup delay + 3 seconds
            "Start-Job -ScriptBlock {",
            "  param($delay, $wrapper, $joinArgs)",
            "  Start-Sleep -Seconds ($delay + 3)",
            "  & $wrapper @joinArgs",
            f"}} -ArgumentList {start_delay}, $squadWrapper, $squadJoinArgs | Out-Null",
            "if ($startupDelay -gt 0) {",
            '  Write-Host "[superCC] async $runtimeLabel startup stagger: waiting $startupDelay seconds"',
            "  Start-Sleep -Seconds $startupDelay",
            "}",
            "$exitCode = 0",
            "for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {",
            '  Write-Host "[superCC] starting $runtimeLabel attempt $attempt/$maxAttempts"',
            "  if ($promptMode -eq 'stdin') {",
            "    $prompt | & $exe @rest",
            "  } else {",
            '    & $exe @rest "$prompt"',
            "  }",
            "  $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }",
            "  if ($exitCode -eq 0) { break }",
            "  if ($attempt -lt $maxAttempts) {",
            "    $retryDelay = [int]([math]::Min(600, $backoffBase * [math]::Pow(2, $attempt - 1)) + (Get-Random -Minimum 0 -Maximum 20))",
            '    Write-Host "[ATTN] state=queued_provider_retry runtime=$runtimeLabel exit=$exitCode backoff_seconds=$retryDelay next_attempt=$($attempt + 1)/$maxAttempts"',
            "    Start-Sleep -Seconds $retryDelay",
            "  }",
            "}",
            "if ($exitCode -ne 0) {",
            '  Write-Host "[ATTN] $runtimeLabel exited with code $exitCode after $maxAttempts attempts"',
            '  Read-Host "Press Enter to close this superCC pane"',
            "}",
        ]
    )

    args = zellij_command_args(
        "run",
        "--cwd",
        str(runtime_process_cwd),
        "--name",
        OFFICES[role]["title"],
        "--direction",
        layout_direction,
        "--",
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encode_powershell(script),
        session=zellij_session,
    )
    return args


def launch_office(
    role: str,
    workspace: Path,
    *,
    court_code: str | None,
    office_client: str,
    hermescli_command: str,
    claude_command: str,
    office_client_command: str | None,
    office_client_args: list[str],
    office_client_prompt_mode: str,
    zellij_session: str | None,
    ministry_mode: str,
    dangerous_yolo: bool,
    codex_start_delay: float,
    codex_retry_attempts: int,
    codex_retry_backoff_base: float,
    layout_direction: str,
    dry_run: bool,
) -> dict[str, Any]:
    dossier = ensure_office_dossier(role, dry_run=dry_run)
    args = build_office_launch_command(
        role,
        workspace,
        court_code=court_code,
        office_client=office_client,
        hermescli_command=hermescli_command,
        claude_command=claude_command,
        office_client_command=office_client_command,
        office_client_args=office_client_args,
        office_client_prompt_mode=office_client_prompt_mode,
        zellij_session=zellij_session,
        ministry_mode=ministry_mode,
        dangerous_yolo=dangerous_yolo,
        codex_start_delay=codex_start_delay,
        codex_retry_attempts=codex_retry_attempts,
        codex_retry_backoff_base=codex_retry_backoff_base,
        layout_direction=layout_direction,
    )
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "role": role,
            "office_client": office_client,
            "ministry_mode": ministry_mode if role in MINISTRY_OFFICES else "awake",
            "codex_start_delay_seconds": round(codex_start_delay, 3),
            "zellij_layout_direction": layout_direction,
            "zellij_layout_policy": SUPERCC_VISIBLE_LAYOUT_POLICY,
            "zellij_session": zellij_session,
            "office_dossier": dossier,
            "office_runtime_cwd": str(office_dossier_dir(role)),
            "runtime_process_cwd": str(runtime_process_cwd_for_client(office_client, role, workspace)),
            "light_bootstrap_policy": SUPERCC_LIGHT_BOOTSTRAP_POLICY,
            "args": compact_command(args),
        }
    result = run_command(args, cwd=workspace, timeout=15)
    result["args"] = compact_command(result.get("args", []))
    result["invocation"] = compact_command(result.get("invocation", []))
    result["role"] = role
    result["office_client"] = office_client
    result["ministry_mode"] = ministry_mode if role in MINISTRY_OFFICES else "awake"
    result["codex_start_delay_seconds"] = round(codex_start_delay, 3)
    result["zellij_layout_direction"] = layout_direction
    result["zellij_layout_policy"] = SUPERCC_VISIBLE_LAYOUT_POLICY
    result["zellij_session"] = zellij_session
    result["office_dossier"] = dossier
    result["office_runtime_cwd"] = str(office_dossier_dir(role))
    result["runtime_process_cwd"] = str(runtime_process_cwd_for_client(office_client, role, workspace))
    result["light_bootstrap_policy"] = SUPERCC_LIGHT_BOOTSTRAP_POLICY
    pane_match = re.search(r"(terminal_\d+|plugin_\d+)", result.get("stdout", ""))
    if pane_match:
        result["pane_id"] = pane_match.group(1)
    # zellij run may not print the created pane id reliably on Windows/MSYS.
    # Re-read the current zellij pane table and bind by the canonical title so
    # restart/turn-start evidence does not drift to a stale terminal_N.
    if result.get("ok") and not dry_run:
        time.sleep(0.5)
        post_zellij = check_zellij(workspace, zellij_session=zellij_session)
        visible = visible_office_panes({"zellij": post_zellij})
        selection = select_unique_visible_pane(visible, role)
        result["post_launch_pane_selection"] = selection
        if selection.get("ok") and selection.get("pane_id"):
            result["pane_id"] = selection.get("pane_id")
    return result


def prioritize_supercc_startup_roles(roles: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Return a deterministic superCC launch order without making 监察 mandatory.

    The newest decree may temporarily skip patrol/监察. Keep 三省 first, then
    六部, 史馆, and optional 监察 for diagnostics; status/reporting order can
    still use STATUS_OFFICES.
    """
    ordered: list[str] = []
    for group in (THREE_OFFICES, MINISTRY_OFFICES, SPECIAL_OFFICES, INSPECTION_OFFICES):
        for role in group:
            if role in roles and role not in ordered:
                ordered.append(role)
    for role in roles:
        if role not in ordered:
            ordered.append(role)
    return tuple(ordered)


def bounded_office_show_delay(value: float | int | str | None) -> float:
    """Clamp presentation-only delay without creating a provider backoff floor."""

    if value is None:
        return SUPERCC_OFFICE_SHOW_DELAY_DEFAULT_SECONDS
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return SUPERCC_OFFICE_SHOW_DELAY_DEFAULT_SECONDS
    if math.isnan(raw):
        return SUPERCC_OFFICE_SHOW_DELAY_DEFAULT_SECONDS
    if raw == math.inf:
        return SUPERCC_OFFICE_SHOW_DELAY_MAX_SECONDS
    if raw == -math.inf:
        return 0.0
    return min(SUPERCC_OFFICE_SHOW_DELAY_MAX_SECONDS, max(0.0, raw))


def office_start_delay(*, index: int, show_delay: float, jitter: float = 0.0) -> float:
    """Return the delay before one visible office; the first office starts now."""

    if index <= 0:
        return 0.0
    return bounded_office_show_delay(
        bounded_office_show_delay(show_delay) + max(0.0, float(jitter or 0.0))
    )


def ordinary_spawn_delay_seconds() -> float:
    """Ordinary spawned subagents never inherit terminal presentation delay."""

    return 0.0


def office_show_delay_resolution(args: argparse.Namespace) -> dict[str, Any]:
    requested = getattr(args, "office_show_delay", None)
    source = "--office-show-delay"
    warnings: list[str] = []
    if requested is None:
        legacy_stagger = getattr(args, "codex_start_stagger", None)
        legacy_launch = getattr(args, "launch_delay", None)
        if legacy_stagger is not None:
            requested = legacy_stagger
            source = "--codex-start-stagger"
            warnings.append("--codex-start-stagger is deprecated; use --office-show-delay")
        elif legacy_launch is not None:
            requested = legacy_launch
            source = "--launch-delay"
            warnings.append("--launch-delay is deprecated for office pacing; use --office-show-delay")
        else:
            requested = SUPERCC_OFFICE_SHOW_DELAY_DEFAULT_SECONDS
            source = "default"

    effective_base = bounded_office_show_delay(requested)
    try:
        requested_float = float(requested)
    except (TypeError, ValueError):
        requested_float = SUPERCC_OFFICE_SHOW_DELAY_DEFAULT_SECONDS
        warnings.append("invalid office show delay replaced by default")
    if not math.isfinite(requested_float) or requested_float != effective_base:
        warnings.append(
            f"office show delay capped_to={effective_base:g}; allowed range is 0-{SUPERCC_OFFICE_SHOW_DELAY_MAX_SECONDS:g} seconds"
        )

    jitter_raw = getattr(args, "codex_start_jitter", SUPERCC_CODEX_START_JITTER_DEFAULT_SECONDS)
    try:
        jitter_requested = max(0.0, float(jitter_raw or 0.0))
    except (TypeError, ValueError):
        jitter_requested = SUPERCC_CODEX_START_JITTER_DEFAULT_SECONDS
        warnings.append("invalid codex start jitter replaced by default")
    if not math.isfinite(jitter_requested):
        jitter_requested = SUPERCC_CODEX_START_JITTER_DEFAULT_SECONDS
        warnings.append("non-finite codex start jitter replaced by default")
    effective_interval = bounded_office_show_delay(effective_base + jitter_requested)
    if effective_base + jitter_requested > SUPERCC_OFFICE_SHOW_DELAY_MAX_SECONDS:
        warnings.append(
            f"office show delay plus jitter capped_to={SUPERCC_OFFICE_SHOW_DELAY_MAX_SECONDS:g} seconds"
        )

    legacy_cooldown = getattr(args, "codex_start_cooldown", None)
    if legacy_cooldown not in (None, 0, 0.0, "0", "0.0"):
        warnings.append("--codex-start-cooldown is deprecated and ignored; the first office has no artificial cooldown")
    legacy_batch_gap = getattr(args, "codex_batch_gap", None)
    if legacy_batch_gap is not None:
        warnings.append("--codex-batch-gap is deprecated; provider queue timing is separate from office presentation")

    return {
        "requested_seconds": requested_float,
        "source": source,
        "base_seconds": effective_base,
        "jitter_requested_seconds": jitter_requested,
        "effective_interval_seconds": effective_interval,
        "capped_to_seconds": SUPERCC_OFFICE_SHOW_DELAY_MAX_SECONDS,
        "first_office_delay_seconds": 0.0,
        "warnings": warnings,
    }


def provider_retry_backoff_seconds(
    configured_seconds: float | int | str | None = None,
    *,
    retry_after_seconds: float | int | str | None = None,
) -> float:
    """Resolve provider retry delay independently from office presentation."""

    configured = SUPERCC_CODEX_RETRY_BACKOFF_DEFAULT_SECONDS if configured_seconds is None else configured_seconds
    try:
        base = max(0.0, float(configured))
    except (TypeError, ValueError):
        base = SUPERCC_CODEX_RETRY_BACKOFF_DEFAULT_SECONDS
    if not math.isfinite(base):
        base = SUPERCC_CODEX_RETRY_BACKOFF_DEFAULT_SECONDS
    if retry_after_seconds is None:
        return base
    try:
        retry_after = max(0.0, float(retry_after_seconds))
    except (TypeError, ValueError):
        return base
    if not math.isfinite(retry_after):
        return base
    return max(base, retry_after)


def requested_rate_limit_per_minute(args: argparse.Namespace) -> int:
    value = int(getattr(args, "request_rate_limit_per_minute", SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE) or SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE)
    return max(1, value)


def request_interval_seconds(args: argparse.Namespace) -> float:
    return 60.0 / requested_rate_limit_per_minute(args)


def estimated_model_request_units_per_launch(args: argparse.Namespace) -> int:
    if getattr(args, "office_client", "codex") == "codex":
        attempts = max(1, int(getattr(args, "codex_retry_attempts", SUPERCC_CODEX_RETRY_ATTEMPTS_DEFAULT) or 1))
        return SUPERCC_CODEX_MODEL_REQUESTS_PER_START_ESTIMATE * attempts
    return 1


def estimated_model_request_units_for_role(args: argparse.Namespace, role: str) -> int:
    if office_client_for_role(args, role) == "codex":
        attempts = max(1, int(getattr(args, "codex_retry_attempts", SUPERCC_CODEX_RETRY_ATTEMPTS_DEFAULT) or 1))
        return SUPERCC_CODEX_MODEL_REQUESTS_PER_START_ESTIMATE * attempts
    return 1


def codex_start_strategy(args: argparse.Namespace) -> str:
    return str(getattr(args, "codex_start_strategy", "sequential") or "sequential")


def codex_batch_size(args: argparse.Namespace) -> int:
    if codex_start_strategy(args) != "batch":
        return 1
    return max(1, int(getattr(args, "codex_batch_size", SUPERCC_CODEX_BATCH_SIZE_DEFAULT) or 1))


def codex_batch_gap_seconds(args: argparse.Namespace) -> float:
    return float(office_show_delay_resolution(args)["effective_interval_seconds"])


def codex_start_cooldown_seconds(args: argparse.Namespace) -> float:
    return 0.0


def codex_start_stagger_seconds(args: argparse.Namespace) -> float:
    return float(office_show_delay_resolution(args)["effective_interval_seconds"])


def provider_launch_queue_plan(
    args: argparse.Namespace,
    roles_to_launch: list[str] | tuple[str, ...],
) -> list[dict[str, Any]]:
    """Schedule provider request windows without changing presentation timing."""

    per_minute = requested_rate_limit_per_minute(args)
    window_index = 0
    used_units = 0
    rows: list[dict[str, Any]] = []
    for index, role in enumerate(roles_to_launch):
        units = estimated_model_request_units_for_role(args, role)
        if used_units and used_units + units > per_minute:
            window_index += 1
            used_units = 0
        blocked = units > per_minute
        offset = float(window_index * 60)
        rows.append(
            {
                "index": index,
                "role": role,
                "estimated_request_units": units,
                "provider_window_index": window_index,
                "provider_queue_offset_seconds": offset,
                "state": "blocked_rate_limit" if blocked else (QUEUED_RATE_LIMIT_STATE if offset > 0 else "ready"),
            }
        )
        used_units += units
    return rows


def request_budget_summary(args: argparse.Namespace, roles_to_launch: list[str] | tuple[str, ...]) -> dict[str, Any]:
    total_limit_raw = getattr(args, "request_total_limit", None)
    total_limit = int(total_limit_raw) if total_limit_raw is not None else None
    per_minute = requested_rate_limit_per_minute(args)
    interval = request_interval_seconds(args)
    planned = len(roles_to_launch)
    role_units = {role: estimated_model_request_units_for_role(args, role) for role in roles_to_launch}
    estimated_units_per_launch = max(role_units.values()) if role_units else 0
    estimated_requests = sum(role_units.values())
    codex_roles = [role for role in roles_to_launch if office_client_for_role(args, role) == "codex"]
    batch_size = codex_batch_size(args) if codex_roles else 1
    estimated_requests_per_batch = SUPERCC_CODEX_MODEL_REQUESTS_PER_START_ESTIMATE * max(1, int(getattr(args, "codex_retry_attempts", SUPERCC_CODEX_RETRY_ATTEMPTS_DEFAULT) or 1)) * batch_size
    over_total = total_limit is not None and estimated_requests > total_limit
    over_batch_rate = bool(codex_roles) and estimated_requests_per_batch > per_minute
    ok = not over_total and not over_batch_rate
    show_delay = office_show_delay_resolution(args)
    provider_queue = provider_launch_queue_plan(args, roles_to_launch)
    return {
        "ok": ok,
        "model_request_budget_gate": "PASSED"
        if ok
        else ("BLOCKED_BATCH_RATE_LIMIT" if over_batch_rate else "BLOCKED_TOTAL_REQUEST_LIMIT"),
        "policy": SUPERCC_REQUEST_LIMIT_POLICY,
        "planned_role_launches": planned,
        "estimated_model_request_units_per_launch": estimated_units_per_launch,
        "estimated_model_request_units_by_role": role_units,
        "codex_retry_attempts_counted": max(1, int(getattr(args, "codex_retry_attempts", SUPERCC_CODEX_RETRY_ATTEMPTS_DEFAULT) or 1))
        if codex_roles
        else None,
        "planned_model_triggering_requests": estimated_requests,
        "request_total_limit": total_limit,
        "request_rate_limit_per_minute": per_minute,
        "request_interval_seconds": interval,
        "provider_rate_limit_state": QUEUED_RATE_LIMIT_STATE,
        "provider_launch_queue": provider_queue,
        "provider_queue_required": any(row["state"] == QUEUED_RATE_LIMIT_STATE for row in provider_queue),
        "provider_retry_backoff_default_seconds": SUPERCC_CODEX_RETRY_BACKOFF_DEFAULT_SECONDS,
        "office_show_delay": show_delay,
        "office_show_delay_seconds": show_delay["effective_interval_seconds"],
        "ordinary_spawn_delay_seconds": ordinary_spawn_delay_seconds(),
        "codex_roles": codex_roles,
        "codex_start_strategy": codex_start_strategy(args) if codex_roles else None,
        "codex_batch_size": batch_size if codex_roles else None,
        "estimated_model_request_units_per_batch": estimated_requests_per_batch if codex_roles else None,
        "codex_batch_gap_seconds": codex_batch_gap_seconds(args) if codex_roles and codex_start_strategy(args) == "batch" else None,
        "codex_start_cooldown_seconds": codex_start_cooldown_seconds(args) if codex_roles else None,
        "effective_codex_start_stagger_seconds": codex_start_stagger_seconds(args) if codex_roles else None,
        "over_total_limit": over_total,
        "over_batch_rate_limit": over_batch_rate,
        "roles_counted_as_model_requests": list(roles_to_launch),
    }


def active_agent_count_over_cap(count: int) -> bool:
    return SUPERCC_SESSION_CAP is not None and count > SUPERCC_SESSION_CAP


def expand_status_selection(selection: str | None) -> tuple[str, ...]:
    if not selection:
        return STATUS_OFFICES
    roles: list[str] = []
    aliases: dict[str, tuple[str, ...]] = {
        "all": STATUS_OFFICES,
        "全部": STATUS_OFFICES,
        "status": STATUS_OFFICES,
        "status-all": STATUS_OFFICES,
        "状态": STATUS_OFFICES,
        "visible-core": ("taizi", *SUPERCC_VISIBLE_CORE_OFFICES),
        "core": ("taizi", *SUPERCC_VISIBLE_CORE_OFFICES),
        "显性核心": ("taizi", *SUPERCC_VISIBLE_CORE_OFFICES),
        "核心": ("taizi", *SUPERCC_VISIBLE_CORE_OFFICES),
        "taizi": ("taizi",),
        "太子": ("taizi",),
    }
    for raw in re.split(r"[,;，；\s]+", selection):
        token = raw.strip()
        if not token:
            continue
        mapped = aliases.get(token)
        if mapped:
            roles.extend(mapped)
            continue
        roles.extend(expand_office_selection(token))
    ordered: list[str] = []
    for role in roles:
        if role not in ordered:
            ordered.append(role)
    return tuple(ordered)


def expand_transport_office_selection(selection: str | None) -> tuple[str, ...]:
    """Expand CLI transport roles, including non-visible lifecycle identities."""

    if not selection:
        return expand_office_selection(selection)
    roles: list[str] = []
    for raw in re.split(r"[,;，；\s]+", selection):
        token = raw.strip()
        if not token:
            continue
        if token in SPECIAL_LIFECYCLE_OFFICES:
            roles.append(token)
            continue
        roles.extend(expand_office_selection(token))
    ordered: list[str] = []
    for role in roles:
        if role not in ordered:
            ordered.append(role)
    return tuple(ordered)


def role_superior(role: str) -> str:
    return direct_superior_metadata(role)["direct_superior"]


def fallback_direct_superior(role: str) -> str:
    if role == "taizi":
        return "user"
    if role in MINISTRY_OFFICES:
        return "shangshu"
    if role in {"shiguan", "shiguan-hermes"}:
        return "taizi/menxia"
    return "taizi"


def direct_superior_metadata(role: str) -> dict[str, str]:
    meta = profile_metadata(role)
    profile = meta.get("profile_fields", {})
    value = profile.get("direct_superior") if isinstance(profile, dict) else None
    if isinstance(value, str) and value.strip():
        return {
            "direct_superior": value.strip(),
            "direct_superior_source": f"standing_profile:{meta.get('profile_source')}",
        }
    return {
        "direct_superior": fallback_direct_superior(role),
        "direct_superior_source": "fallback_role_map",
    }


def build_mode_records(
    roles: tuple[str, ...] | list[str],
    *,
    default_mode: str,
    reason: str,
    unfinished: set[str] | None = None,
    ministry_mode: str | None = None,
) -> dict[str, dict[str, Any]]:
    unfinished = unfinished or set()
    records: dict[str, dict[str, Any]] = {}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for role in roles:
        mode = ministry_mode if role in MINISTRY_OFFICES and ministry_mode else default_mode
        if role in unfinished:
            mode = "awake_unfinished"
        records[role] = {
            "mode": mode,
            "reason": reason,
            "unfinished": role in unfinished,
            "updated_at": now,
        }
        records[role].update(direct_superior_metadata(role))
        profile = profile_metadata(role)
        records[role].update(
            {
                "office_profile_loaded": profile["office_profile_loaded"],
                "profile_source": profile["profile_source"],
                "profile_hash": profile["profile_hash"],
                "profile_version": profile["profile_version"],
                "profile_missing_fields": profile["profile_missing_fields"],
            }
        )
    return records


def launch_offices(args: argparse.Namespace, roles: tuple[str, ...]) -> dict[str, Any]:
    special_preflight = special_lifecycle_transport_preflight(
        args,
        roles,
        transport_action="launch_offices",
    )
    if not special_preflight["ok"]:
        return special_preflight
    if getattr(args, "skip_inspector", False):
        roles = tuple(role for role in roles if role not in INSPECTION_OFFICES)
    if any(role in INSPECTION_OFFICES for role in roles):
        return {
            "ok": False,
            "supercc_env_gate": "runtime_degraded",
            "visible_display_gate": "runtime_degraded",
            "display_transport_gate": "runtime_degraded",
            "office_client_gate": "not_checked",
            "reason": "legacy visible patrol-inspector launch is disabled; use scripts/supercc_watchdog.py for 429/close/silence supervision",
            "requested_roles": list(roles),
            "watchdog_script": SUPERCC_WATCHDOG_SCRIPT,
        }
    roles = prioritize_supercc_startup_roles(roles)
    workspace = Path(args.workspace).resolve()
    office_client = check_office_client(args, workspace)
    office_clients_by_role = check_office_clients_for_roles(args, workspace, roles)
    check = supercc_check_for_args(args, workspace)
    actions: list[dict[str, Any]] = []
    if not check["passed"] and not args.force:
        return {
            "ok": False,
            "supercc_env_gate": check["supercc_env_gate"],
            "visible_display_gate": check["visible_display_gate"],
            "display_transport_gate": check["display_transport_gate"],
            "office_client_gate": check["office_client_gate"],
            "reason": "environment gate did not pass; use --force only for diagnostics",
            "check": check,
            "office_client": office_client,
            "office_clients_by_role": office_clients_by_role,
            "actions": actions,
        }
    if (not office_client["available"] or not office_clients_by_role["available"]) and not args.force and not args.dry_run:
        return {
            "ok": False,
            "supercc_env_gate": "runtime_degraded",
            "visible_display_gate": check["visible_display_gate"],
            "display_transport_gate": check["display_transport_gate"],
            "office_client_gate": "runtime_degraded",
            "reason": "one or more selected office clients are unavailable; set the matching command/env or use --force for diagnostics",
            "check": check,
            "office_client": office_client,
            "office_clients_by_role": office_clients_by_role,
            "actions": actions,
        }

    agents_json = check["squad"].get("agents_json", [])
    if args.archive_test_agents:
        actions.append({"archive_test_agents": archive_test_agents(workspace, agents_json, dry_run=args.dry_run)})
    if args.reclaim_existing:
        actions.append({"archive_duplicate_core_agents": archive_duplicate_core_agents(workspace, agents_json, dry_run=args.dry_run)})
        if not args.dry_run:
            check = supercc_check_for_args(args, workspace)
            agents_json = check["squad"].get("agents_json", [])
    zellij_session = current_zellij_session(check)
    active_ids = active_agent_ids(agents_json)
    visible = visible_office_panes(check)
    duplicates = {
        role: rows
        for role, rows in visible.items()
        if role in roles and len(rows) > 1
    }
    reused: list[dict[str, Any]] = []
    degraded: list[dict[str, Any]] = []
    roles_to_launch: list[str] = []
    for role in roles:
        role_rows = active_rows_for_role(check, role)
        active_role_ids = [str(row.get("id", "")) for row in role_rows if row.get("id")]
        duplicate_identity_ids = [agent_id for agent_id in active_role_ids if agent_id != role]
        if len(role_rows) > 1 or duplicate_identity_ids:
            if args.reclaim_existing:
                roles_to_launch.append(role)
                actions.append(
                    {
                        "reclaim_duplicate_squad_identity": {
                            "role": role,
                            "active_squad_ids_for_role": active_role_ids,
                            "duplicate_identity_ids": duplicate_identity_ids,
                        }
                    }
                )
                continue
            degraded.append(
                {
                    "role": role,
                    "reason": "duplicate_active_squad_identities_for_role",
                    "active_squad_ids_for_role": active_role_ids,
                    "duplicate_identity_ids": duplicate_identity_ids,
                }
            )
            continue
        panes = visible.get(role, [])
        if len(panes) > 1:
            if args.reclaim_existing:
                roles_to_launch.append(role)
                actions.append(
                    {
                        "reclaim_duplicate_visible_panes": {
                            "role": role,
                            "pane_ids": [pane["pane_id"] for pane in panes],
                            "titles": [pane.get("title") for pane in panes],
                        }
                    }
                )
                continue
            degraded.append(
                {
                    "role": role,
                    "reason": "duplicate_current_zellij_panes_for_role",
                    "title": OFFICES[role]["title"],
                    "pane_ids": [pane["pane_id"] for pane in panes],
                }
            )
            continue
        if panes and role in active_ids:
            reused.append(
                {
                    "role": role,
                    "title": OFFICES[role]["title"],
                    "pane_ids": [pane["pane_id"] for pane in panes],
                    "duplicate_count": len(panes),
                }
            )
            continue
        if panes and role not in active_ids:
            if args.reclaim_existing:
                roles_to_launch.append(role)
                actions.append(
                    {
                        "reclaim_visible_pane_without_identity": {
                            "role": role,
                            "pane_ids": [pane["pane_id"] for pane in panes],
                            "titles": [pane.get("title") for pane in panes],
                        }
                    }
                )
                continue
            degraded.append(
                {
                    "role": role,
                    "reason": "visible_pane_without_active_squad_identity",
                    "title": OFFICES[role]["title"],
                    "pane_ids": [pane["pane_id"] for pane in panes],
                }
            )
            continue
        roles_to_launch.append(role)

    reclaim_ids = tuple(roles_to_launch) if args.reclaim_existing else ()
    # Close stale panes before reclaiming squad identities
    for role in reclaim_ids:
        role_panes = visible.get(role, [])
        for pane in role_panes:
            pane_id = pane.get('pane_id')
            if pane_id:
                close_result = close_pane(str(pane_id), args.dry_run, zellij_session=zellij_session)
                actions.append({"close_stale_pane": {"role": role, "pane_id": pane_id, "result": close_result}})

    for agent_id in reclaim_ids:
        archived = maybe_archive_existing(
            agent_id,
            workspace,
            agents_json,
            reclaim_existing=True,
            dry_run=args.dry_run,
        )
        if archived:
            actions.append({"archive_existing": agent_id, "result": archived})

    taizi_selection = select_unique_visible_pane(visible, "taizi")
    taizi_pane_id = taizi_selection.get("pane_id") if taizi_selection.get("ok") else current_pane_id()
    actions.append(
        {
            "rename_taizi_pane": rename_taizi_pane(
                args.dry_run,
                pane_id=str(taizi_pane_id) if taizi_pane_id else None,
                zellij_session=zellij_session,
            )
        }
    )
    if "taizi" in active_ids:
        actions.append({"join_taizi": {"ok": True, "reused": True, "actual_id": "taizi"}})
    else:
        actions.append({"join_taizi": join_agent("taizi", "taizi", workspace, args.dry_run, office_client=office_client_for_role(args, "taizi"))})

    roles_to_launch = list(prioritize_supercc_startup_roles(roles_to_launch))
    if any(office_client_for_role(args, role) == "claude" for role in roles_to_launch):
        claude_trust_paths = [office_dossier_dir(role) for role in roles_to_launch]
        if workspace != Path.home().resolve():
            claude_trust_paths.append(workspace)
        actions.append(
            {
                "claude_project_trust": ensure_claude_project_trust(
                    claude_trust_paths,
                    dry_run=args.dry_run,
                )
            }
        )
    request_budget = request_budget_summary(args, roles_to_launch)
    actions.append({"model_request_budget": request_budget})
    if not request_budget["ok"]:
        return {
            "ok": False,
            "supercc_env_gate": check["supercc_env_gate"],
            "visible_display_gate": check["visible_display_gate"],
            "display_transport_gate": check["display_transport_gate"],
            "office_client_gate": check["office_client_gate"],
            "standing_officials": "BLOCKED_TOTAL_REQUEST_LIMIT",
            "model_request_budget": request_budget,
            "visible_offices_requested": list(roles),
            "visible_offices_reused": reused,
            "visible_offices_to_launch": roles_to_launch,
            "visible_office_degraded": degraded,
            "check": check,
            "actions": actions,
        }
    actions.append(
        {
            "optional_inspector_startup_policy": {
                "required": False,
                "enabled": inspector_enabled(args),
                "skip_inspector": bool(getattr(args, "skip_inspector", False)),
                "launch_order": roles_to_launch,
                "reason": "dedicated 监察 pane is removed from routine startup; launch order is governed by role hierarchy plus request-rate budget",
            }
        }
    )

    launches: list[dict[str, Any]] = []
    patrol_diagnostic_baseline: dict[str, Any] | None = None
    layout_actions: list[dict[str, Any]] = []
    right_column_anchor_pane_id: str | None = None
    show_delay = request_budget["office_show_delay"]
    provider_queue_rows = request_budget["provider_launch_queue"]
    provider_queue_started = time.monotonic()
    for index, role in enumerate(roles_to_launch):
        role_client = office_client_for_role(args, role)
        provider_row = provider_queue_rows[index]
        provider_offset = float(provider_row["provider_queue_offset_seconds"])
        elapsed = 0.0 if args.dry_run else max(0.0, time.monotonic() - provider_queue_started)
        provider_wait = max(0.0, provider_offset - elapsed)
        provider_event = {
            **provider_row,
            "provider_queue_wait_seconds": round(provider_wait, 3),
            "presentation_delay": False,
        }
        if provider_wait > 0:
            actions.append({"provider_rate_limit_queue": provider_event})
            if not args.dry_run:
                print(
                    f"[superCC] state={QUEUED_RATE_LIMIT_STATE} role={role} "
                    f"wait_seconds={provider_wait:.3f} provider_window={provider_row['provider_window_index']}",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(provider_wait)

        jitter_max = float(show_delay["jitter_requested_seconds"])
        jitter = random.uniform(0.0, jitter_max) if jitter_max > 0.0 else 0.0
        presentation_wait = office_start_delay(
            index=index,
            show_delay=float(show_delay["base_seconds"]),
            jitter=jitter,
        )
        if presentation_wait > 0:
            actions.append(
                {
                    "office_show_delay": {
                        "role": role,
                        "index": index,
                        "state": "office_show_delay",
                        "seconds": round(presentation_wait, 3),
                        "capped_to_seconds": SUPERCC_OFFICE_SHOW_DELAY_MAX_SECONDS,
                        "provider_backoff": False,
                    }
                }
            )
            if not args.dry_run:
                time.sleep(presentation_wait)

        if index == 0:
            focus_target = taizi_pane_id
            layout_direction = "right"
        else:
            focus_target = right_column_anchor_pane_id or taizi_pane_id
            layout_direction = "down" if right_column_anchor_pane_id else "right"
        focus_result = focus_pane(focus_target, args.dry_run, zellij_session=zellij_session)
        layout_actions.append(
            {
                "role": role,
                "focus_target_pane_id": focus_target,
                "focus_result": focus_result,
                "zellij_layout_direction": layout_direction,
                "zellij_layout_policy": SUPERCC_VISIBLE_LAYOUT_POLICY,
            }
        )
        codex_start_delay = 0.0
        launch = launch_office(
            role,
            workspace,
            court_code=args.court_code,
            office_client=role_client,
            hermescli_command=args.hermescli_command,
            claude_command=args.claude_command,
            office_client_command=office_client_command_for_role(args, role),
            office_client_args=office_client_extra_args_for_role(args, role),
            office_client_prompt_mode=office_client_prompt_mode_for_role(args, role),
            zellij_session=zellij_session,
            ministry_mode=args.ministry_mode,
            dangerous_yolo=args.dangerous_yolo,
            codex_start_delay=codex_start_delay,
            codex_retry_attempts=args.codex_retry_attempts,
            codex_retry_backoff_base=args.codex_retry_backoff_base,
            layout_direction=layout_direction,
            dry_run=args.dry_run,
        )
        launch["office_show_delay_before_start_seconds"] = round(presentation_wait, 3)
        launch["provider_queue_wait_seconds"] = round(provider_wait, 3)
        launch["provider_queue_state"] = provider_row["state"]
        launches.append(launch)
        if launch.get("pane_id"):
            right_column_anchor_pane_id = str(launch.get("pane_id"))
        elif args.dry_run:
            right_column_anchor_pane_id = f"planned_right_column_after_{role}"
        if role in INSPECTION_OFFICES:
            patrol_diagnostic_baseline = {
                "ok": bool(launch.get("ok", False)),
                "role": role,
                "diagnostic_only": True,
                "status": "DIAGNOSTIC_BASELINE_ESTABLISHED" if launch.get("ok", False) or args.dry_run else "RUNTIME_DEGRADED",
                "reason": "patrol-inspector launch is explicit diagnostic only; routine startup uses hierarchical supervision",
            }
            actions.append({"patrol_diagnostic_baseline": patrol_diagnostic_baseline})
    actions.append({"visible_layout": {"policy": SUPERCC_VISIBLE_LAYOUT_POLICY, "actions": layout_actions}})
    actions.append({"launches": launches})
    actions.append(
        {
            "record_office_state": write_office_state(
                workspace,
                build_mode_records(
                    roles,
                    default_mode="awake",
                    ministry_mode=args.ministry_mode,
                    reason="launch_or_reuse",
                ),
                zellij_session=zellij_session,
                dry_run=args.dry_run,
            )
        }
    )

    post_check = None if args.dry_run else supercc_check_for_args(args, workspace)
    launched_ok = all(item.get("ok", False) for item in launches)
    final_visible = visible_office_panes(post_check) if post_check else visible
    duplicate_visible_panes = {
        role: [{"pane_id": pane["pane_id"], "title": pane["title"]} for pane in panes]
        for role, panes in final_visible.items()
        if role in roles and len(panes) > 1
    }
    if args.dry_run:
        standing_officials = "DRY_RUN"
    elif duplicate_visible_panes or degraded:
        standing_officials = "RUNTIME_DEGRADED"
    elif launches and reused:
        standing_officials = "LAUNCHED_OR_REUSED"
    elif launches:
        standing_officials = "LAUNCHED"
    else:
        standing_officials = "REUSED"
    return {
        "ok": launched_ok and not degraded and not duplicate_visible_panes and check["passed"],
        "supercc_env_gate": check["supercc_env_gate"],
        "visible_display_gate": check["visible_display_gate"],
        "display_transport_gate": check["display_transport_gate"],
        "office_client_gate": check["office_client_gate"],
        "standing_officials": standing_officials,
        "office_client": office_client,
        "ministry_mode": args.ministry_mode,
        "supercc_visible_core_roles": list(SUPERCC_VISIBLE_CORE_OFFICES),
        "silent_supervisor": "NOT_STARTED",
        "supercc_watchdog": "NOT_APPLICABLE",
        "watchdog_no_visible_window": True,
        "legacy_patrol_visible_pane": "disabled",
        "silent_supervisor_policy": SILENT_SUPERVISOR_POLICY,
        "zellij_visible_layout_policy": SUPERCC_VISIBLE_LAYOUT_POLICY,
        "supervision_channel": SUPERVISION_CHANNEL,
        "supervision_evidence": "PASSED",
        "six_ministry_step_plan_policy": SIX_MINISTRY_STEP_PLAN_POLICY,
        "supercc_request_limit_policy": SUPERCC_REQUEST_LIMIT_POLICY,
        "model_request_budget": request_budget,
        "request_rate_limit_per_minute": request_budget["request_rate_limit_per_minute"],
        "request_interval_seconds": request_budget["request_interval_seconds"],
        "office_show_delay": request_budget.get("office_show_delay"),
        "office_show_delay_seconds": request_budget.get("office_show_delay_seconds"),
        "ordinary_spawn_delay_seconds": request_budget.get("ordinary_spawn_delay_seconds"),
        "provider_rate_limit_state": request_budget.get("provider_rate_limit_state"),
        "provider_queue_required": request_budget.get("provider_queue_required"),
        "codex_start_cooldown_seconds": request_budget.get("codex_start_cooldown_seconds"),
        "effective_codex_start_stagger_seconds": request_budget.get("effective_codex_start_stagger_seconds"),
        "codex_start_strategy": request_budget.get("codex_start_strategy"),
        "codex_batch_size": request_budget.get("codex_batch_size"),
        "estimated_model_request_units_per_batch": request_budget.get("estimated_model_request_units_per_batch"),
        "codex_batch_gap_seconds": request_budget.get("codex_batch_gap_seconds"),
        "visible_offices_requested": list(roles),
        "special_lifecycle_preflight": special_preflight["special_lifecycle_preflight"],
        "visible_offices_reused": reused,
        "visible_offices_to_launch": roles_to_launch,
        "visible_office_degraded": degraded,
        "duplicate_visible_panes": duplicate_visible_panes,
        "check": check,
        "post_check": post_check,
        "office_clients_by_role": office_clients_by_role,
        "supercc_super_entry_policy": SUPERCC_SUPER_ENTRY_POLICY,
        "actions": actions,
    }


def launch_three(args: argparse.Namespace) -> dict[str, Any]:
    return launch_offices(args, THREE_OFFICES)


def launch_visible_core(args: argparse.Namespace) -> dict[str, Any]:
    return launch_offices(args, SUPERCC_VISIBLE_CORE_OFFICES)


def check_only(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    payload = supercc_check_for_args(args, workspace)
    check_roles = ("taizi", *SUPERCC_VISIBLE_CORE_OFFICES)
    visible = visible_office_panes(payload)
    uniqueness = {
        role: office_uniqueness_gate(payload, visible, role)
        for role in check_roles
    }
    payload["visible_office_uniqueness_gate"] = uniqueness
    if not all(item.get("ok") for item in uniqueness.values()):
        payload["visible_display_gate"] = "runtime_degraded"
        payload["display_transport_gate"] = "runtime_degraded"
        payload["supercc_env_gate"] = "runtime_degraded"
        payload["passed"] = False
    payload["office_clients_by_role"] = check_office_clients_for_roles(
        args,
        workspace,
        check_roles,
        check=payload,
    )
    if not payload["office_clients_by_role"].get("available"):
        payload["office_client_gate"] = "runtime_degraded"
        payload["supercc_env_gate"] = "runtime_degraded"
        payload["passed"] = False
    payload["check_only_roles"] = list(check_roles)
    payload["blank_environment_policy"] = "check-only reads packaged skill files and PATH-resolved tools; it does not require Shiguan state, memory, or prior runtime records"
    return payload


def rename_taizi_only(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    check = supercc_check_for_args(args, workspace)
    actions: list[dict[str, Any]] = []
    agents_json = check["squad"].get("agents_json", [])
    archived = maybe_archive_existing(
        "taizi",
        workspace,
        agents_json,
        reclaim_existing=args.reclaim_existing,
        dry_run=args.dry_run,
    )
    if archived:
        actions.append({"archive_existing": "taizi", "result": archived})
    visible = visible_office_panes(check)
    taizi_selection = select_unique_visible_pane(visible, "taizi")
    taizi_pane_id = taizi_selection.get("pane_id") if taizi_selection.get("ok") else current_pane_id()
    actions.append(
        {
            "rename_taizi_pane": rename_taizi_pane(
                args.dry_run,
                pane_id=str(taizi_pane_id) if taizi_pane_id else None,
                zellij_session=current_zellij_session(check),
            )
        }
    )
    actions.append({"join_taizi": join_agent("taizi", "taizi", workspace, args.dry_run)})
    return {"ok": check["passed"], "check": check, "actions": actions}


def parse_office_set(selection: str | None) -> set[str]:
    if not selection:
        return set()
    return set(expand_status_selection(selection))


def silence_roles(
    args: argparse.Namespace,
    roles: tuple[str, ...],
    *,
    unfinished: set[str],
    reason: str,
    sender: str = "taizi",
    protected_roles: tuple[str, ...] = MONITOR_NO_SILENCE_ROLES,
    default_mode: str = "silent",
    protected_mode: str = "awake_no_silence",
    notify_inspector_expected_silence: bool = False,
) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    check = supercc_check_for_args(args, workspace)
    active_ids = active_agent_ids(check["squad"].get("agents_json", []))
    protected = set(protected_roles)
    to_silence = [role for role in roles if role not in unfinished and role not in protected]
    kept_awake = [role for role in roles if role in protected or role in unfinished]
    notices: list[dict[str, Any]] = []
    for role in to_silence:
        if role not in active_ids:
            notices.append({"role": role, "skipped": True, "reason": "no_active_squad_identity"})
            continue
        message = (
            f"[SILENCE] reason={reason}; mode={default_mode}; stay idle, do not run commands, "
            "and wait for an explicit new decree or superior wake dispatch. "
            "Expected silence is recorded in Shiguan and mirrored to patrol only when explicit diagnostics are active."
        )
        notices.append({"role": role, "result": send_squad_notice(workspace, sender, role, message, args.dry_run)})
    inspector_notice: dict[str, Any] | None = None
    if notify_inspector_expected_silence and inspector_enabled(args) and "patrol-inspector" in active_ids:
        expected = ",".join(to_silence)
        message = (
            "[CLOSEOUT_WATCH] 结诏收束已发；expected_silenced_roles="
            f"{expected}; expected_mode={default_mode}; do not report these roles as abnormal solely "
            "because they are idle_receive/silent after closeout. Keep only the status table visible; "
            "report or trigger hierarchy only for crash, 429, duplicate pane, new decree wake failure, "
            "or roles not in the expected_silenced list."
        )
        inspector_notice = {
            "role": "patrol-inspector",
            "result": send_squad_notice(workspace, sender, "patrol-inspector", message, args.dry_run),
        }
        notices.append(inspector_notice)
    modes: dict[str, dict[str, Any]] = {}
    if to_silence:
        modes.update(build_mode_records(tuple(to_silence), default_mode=default_mode, reason=reason, unfinished=unfinished))
    if kept_awake:
        modes.update(
            build_mode_records(
                tuple(kept_awake),
                default_mode=protected_mode,
                reason=f"{reason}: protected/unfinished roles stay awake as specified",
                unfinished=unfinished,
            )
        )
    state = write_office_state(workspace, modes, zellij_session=current_zellij_session(check), dry_run=args.dry_run)
    return {
        "ok": True,
        "supercc_env_gate": check.get("supercc_env_gate"),
        "visible_display_gate": check.get("visible_display_gate"),
        "display_transport_gate": check.get("display_transport_gate"),
        "office_client_gate": check.get("office_client_gate"),
        "reason": reason,
        "taizi_no_silence": "taizi" in NO_SILENCE_ROLES,
        "three_departments_no_silence": all(role in NO_SILENCE_ROLES for role in THREE_OFFICES),
        "no_silence_roles": list(NO_SILENCE_ROLES),
        "monitor_no_silence_roles": list(MONITOR_NO_SILENCE_ROLES),
        "silent_supervisor": "NOT_STARTED",
        "supercc_watchdog": "NOT_APPLICABLE",
        "watchdog_no_visible_window": True,
        "legacy_patrol_visible_pane": "disabled",
        "silent_supervisor_policy": SILENT_SUPERVISOR_POLICY,
        "closeout_silence_policy": CLOSEOUT_SILENCE_POLICY,
        "supervision_channel": SUPERVISION_CHANNEL,
        "supervision_evidence": "PASSED",
        "check": check,
        "silenced": to_silence,
        "expected_silenced_roles_for_supervisor": to_silence,
        "inspector_notice": inspector_notice,
        "kept_awake_no_silence": kept_awake,
        "unfinished_kept_awake": sorted(unfinished),
        "notices": notices,
        "state": state,
    }


def wake_roles(args: argparse.Namespace, roles: tuple[str, ...], *, reason: str, sender: str = "shangshu") -> dict[str, Any]:
    special_preflight = special_lifecycle_transport_preflight(
        args,
        roles,
        transport_action="wake_roles",
        sender=sender,
    )
    if not special_preflight["ok"]:
        return special_preflight
    workspace = Path(args.workspace).resolve()
    check = supercc_check_for_args(args, workspace)
    active_ids = active_agent_ids(check["squad"].get("agents_json", []))
    visible = visible_office_panes(check)
    notices: list[dict[str, Any]] = []
    ministry_non_visible_dispatch = bool(set(roles) & set(MINISTRY_OFFICES))
    special_lifecycle_non_visible_dispatch = bool(
        set(roles) & set(SPECIAL_LIFECYCLE_OFFICES)
    )
    non_visible_structured_dispatch = (
        ministry_non_visible_dispatch or special_lifecycle_non_visible_dispatch
    )
    for role in roles:
        if role not in active_ids:
            notices.append({"role": role, "skipped": True, "reason": "no_active_squad_identity"})
            continue
        uniqueness = office_uniqueness_gate(
            check,
            visible,
            role,
            require_visible=role not in (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES),
        )
        if not uniqueness.get("ok"):
            notices.append(
                {
                    "role": role,
                    "skipped": True,
                    "reason": "office_uniqueness_gate_failed",
                    "office_uniqueness_gate": uniqueness,
                }
            )
            continue
        message = f"[WAKE_DISPATCH] reason={reason}; mode=awake; accept one bounded assignment from {sender}."
        notices.append({"role": role, "result": send_squad_notice(workspace, sender, role, message, args.dry_run)})
    phase_cycle = supercc_phase_for_roles(roles, sender=sender)
    inspector_wake_cc = maybe_send_inspector_wake_cc(
        args,
        workspace,
        sender,
        roles,
        reason=reason,
        expected_mode="task_queued_non_visible" if non_visible_structured_dispatch else "awake",
    )
    state_records = build_mode_records(roles, default_mode="awake", reason=reason)
    for role in state_records:
        state_records[role].update(
            {
                "supercc_phase_cycle": phase_cycle,
                "inspector_wake_cc_policy": INSPECTOR_WAKE_CC_POLICY,
                "inspector_wake_cc": inspector_wake_cc,
                "wake_cc_to_patrol_inspector": inspector_enabled(args),
                "supervision_channel": SUPERVISION_CHANNEL,
                "supervision_evidence": "PASSED",
                "special_lifecycle_preflight": special_preflight["special_lifecycle_preflight"],
            }
        )
    state = write_office_state(
        workspace,
        state_records,
        zellij_session=current_zellij_session(check),
        dry_run=args.dry_run,
    )
    return {
        "ok": True,
        "reason": reason,
        "woken": list(roles),
        "supercc_phase_cycle": phase_cycle,
        "inspector_wake_cc_policy": INSPECTOR_WAKE_CC_POLICY,
        "inspector_wake_cc": inspector_wake_cc,
        "wake_cc_to_patrol_inspector": inspector_enabled(args),
        "supervision_channel": SUPERVISION_CHANNEL,
        "supervision_evidence": "PASSED",
        "special_lifecycle_preflight": special_preflight["special_lifecycle_preflight"],
        "notices": notices,
        "state": state,
    }


def mark_turn_start_open_decree(args: argparse.Namespace, check: dict[str, Any], *, native_wake: bool = True) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    zellij_session = current_zellij_session(check)
    active_ids = active_agent_ids(check["squad"].get("agents_json", []))
    visible = visible_office_panes(check)
    reason = "turn_start_open_decree_receive; revive taizi/three-departments from post-closeout idle_receive"
    notices: list[dict[str, Any]] = []
    native_wakes: list[dict[str, Any]] = []
    message = (
        "[TURN_START_OPEN_DECREE] mode=awake_no_silence; 结诏后静默已解除；"
        "resume receive/heartbeat posture for this superCC turn. Do only your named-office duty; "
        "do not substitute for another office."
    )
    for role in NO_SILENCE_ROLES:
        if role not in active_ids:
            notices.append({"role": role, "skipped": True, "reason": "no_active_squad_identity"})
            continue
        if role == "taizi":
            sender = "zhongshu" if "zhongshu" in active_ids else "taizi"
        else:
            sender = "taizi"
        notices.append({"role": role, "result": send_squad_notice(workspace, sender, role, message, args.dry_run)})
        pane_selection = select_unique_visible_pane(visible, role)
        pane = pane_selection.get("pane") if pane_selection.get("ok") else None
        if not native_wake:
            native_wakes.append(
                {
                    "role": role,
                    "ok": True,
                    "skipped": True,
                    "reason": "native_turn_start_wake_suppressed_after_restart; freshly launched wrapper panes receive startup prompt after rate-limit cooldown",
                    "visible_pane_selection": pane_selection,
                    "pane_id": pane.get("pane_id") if pane else None,
                }
            )
            continue
        if role == "taizi":
            native_wakes.append(
                {
                    "role": role,
                    "ok": True,
                    "skipped": True,
                    "reason": "taizi_root_pane_not_native_prompted; root pane receives decree through wrapper receive and user-visible transcript",
                    "visible_pane_selection": pane_selection,
                    "pane_id": pane.get("pane_id") if pane else None,
                }
            )
            continue
        if not pane:
            native_wakes.append(
                {
                    "role": role,
                    "ok": False,
                    "reason": pane_selection.get("reason", "no_visible_pane_for_native_wake"),
                    "visible_pane_selection": pane_selection,
                }
            )
            continue
        prompt = build_native_receive_command_prompt(role, action="turn_start_open_decree")
        native_wakes.append(
            {
                "role": role,
                "pane_id": pane["pane_id"],
                "visible_pane_selection": pane_selection,
                "result": native_pane_enter_sequence(
                    workspace,
                    pane["pane_id"],
                    prompt,
                    dry_run=args.dry_run,
                    zellij_session=zellij_session,
                    payload_kind=NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND,
                    squad_delivery_order=SQUAD_NOTICE_BEFORE_NATIVE_ENTER,
                ),
            }
        )
    modes = build_mode_records(NO_SILENCE_ROLES, default_mode="awake_no_silence", reason=reason)
    state = write_office_state(workspace, modes, zellij_session=zellij_session, dry_run=args.dry_run)
    failed_notices = [
        notice
        for notice in notices
        if not notice.get("skipped") and not bool((notice.get("result") or {}).get("ok"))
    ]
    failed_native_wakes = [
        wake
        for wake in native_wakes
        if not bool((wake.get("result") or wake).get("ok"))
    ]
    return {
        "ok": bool(state.get("ok")) and not failed_notices and not failed_native_wakes,
        "turn_start_open_decree": "PASSED" if not failed_notices and not failed_native_wakes else "PARTIAL",
        "reason": reason,
        "roles": list(NO_SILENCE_ROLES),
        "taizi_reawakened_from_closeout_idle": True,
        "three_departments_reawakened_from_closeout_idle": True,
        "no_silence_roles": list(NO_SILENCE_ROLES),
        "turn_start_native_wake_policy": TURN_START_NATIVE_WAKE_POLICY,
        "native_turn_start_wake": native_wakes,
        "physical_enter_byte": PHYSICAL_ENTER_BYTE,
        "notices": notices,
        "state": state,
    }


def release_noncurrent_inactive(
    workspace: Path,
    check: dict[str, Any],
    roles: tuple[str, ...],
    *,
    inactive_age_seconds: float,
    dry_run: bool,
) -> dict[str, Any]:
    agents_by_id = active_agents_by_id(check["squad"].get("agents_json", []))
    visible = visible_office_panes(check)
    cleanup = noncurrent_inactive_cleanup_evaluator(
        workspace,
        check,
        roles,
        inactive_age_seconds=inactive_age_seconds,
        include_task_probe=True,
    )["noncurrent_inactive_pane_cleanup"]
    eligible_roles = set(cleanup["eligible_roles"])
    health: list[dict[str, Any]] = []
    released: list[dict[str, Any]] = []
    for role in roles:
        row = agents_by_id.get(role)
        panes = visible.get(role, [])
        response = simple_response_status(row, inactive_age_seconds=inactive_age_seconds)
        in_current_zellij_workspace = bool(panes)
        reusable = in_current_zellij_workspace and response["ok"]
        health_row = {
            "role": role,
            "agent_active": row is not None,
            "in_current_zellij_workspace": in_current_zellij_workspace,
            "pane_ids": [pane["pane_id"] for pane in panes],
            "simple_response": response,
            "reusable": reusable,
        }
        if role in eligible_roles:
            result = archive_agent(role, workspace, dry_run)
            health_row["released_as_noncurrent_inactive"] = True
            released.append({"role": role, "agent_id": role, "result": result})
        health.append(health_row)
    record = {
        "schema": SUPERCC_HEALTH_SCHEMA,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "workspace": str(workspace),
        "zellij_session": current_zellij_session(check),
        "roles": health,
        "released": released,
        "noncurrent_inactive_cleanup": cleanup,
    }
    return {"ok": True, "health": health, "released": released, "noncurrent_inactive_cleanup": cleanup, "record": append_turn_health(record, dry_run)}


def turn_start(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    requested_roles = expand_office_selection(args.turn_start or "visible-core")
    roles = prioritize_supercc_startup_roles(tuple(role for role in requested_roles if role in SUPERCC_VISIBLE_CORE_OFFICES) or SUPERCC_VISIBLE_CORE_OFFICES)
    health_roles = ALL_VISIBLE_OFFICES
    check = supercc_check_for_args(args, workspace)
    actions: list[dict[str, Any]] = []
    if not check["passed"] and not args.force:
        return {
            "ok": False,
            "supercc_env_gate": check["supercc_env_gate"],
            "visible_display_gate": check["visible_display_gate"],
            "display_transport_gate": check["display_transport_gate"],
            "office_client_gate": check["office_client_gate"],
            "reason": "environment gate did not pass; use --force only for diagnostics",
            "check": check,
            "actions": actions,
        }
    release = release_noncurrent_inactive(
        workspace,
        check,
        health_roles,
        inactive_age_seconds=args.inactive_age_seconds,
        dry_run=args.dry_run,
    )
    actions.append({"turn_start_health": release})
    launch = launch_offices(args, roles)
    actions.append({"ensure_visible_offices": launch})
    post_launch_check = supercc_check_for_args(args, workspace)
    open_decree = mark_turn_start_open_decree(args, post_launch_check)
    actions.append({"turn_start_open_decree": open_decree})
    silence = silence_roles(
        args,
        NON_VISIBLE_DEFAULT_SILENT_OFFICES,
        unfinished=set(),
        reason="turn_start_default_silent_until_shangshu_dispatch",
        sender="shangshu",
    )
    actions.append({"default_silence_ministries": silence})
    supervisor_status = {
        "ok": True,
        "silent_supervisor": "NOT_STARTED",
        "supercc_watchdog": "NOT_APPLICABLE",
        "watchdog_process": "NOT_APPLICABLE",
        "watchdog_no_visible_window": True,
        "watchdog_daemon_start": "NOT_APPLICABLE",
        "watchdog_daemon_stop": "NOT_APPLICABLE",
        "legacy_patrol_visible_pane": "disabled",
        "policy": SILENT_SUPERVISOR_POLICY,
    }
    actions.append({"silent_supervisor_status": supervisor_status})
    ok = bool(launch.get("ok")) and bool(release.get("ok")) and bool(open_decree.get("ok")) and bool(silence.get("ok")) and bool(supervisor_status.get("ok"))
    return {
        "ok": ok,
        "supercc_env_gate": launch.get("supercc_env_gate", check["supercc_env_gate"]),
        "visible_display_gate": launch.get("visible_display_gate", check["visible_display_gate"]),
        "display_transport_gate": launch.get("display_transport_gate", check["display_transport_gate"]),
        "office_client_gate": launch.get("office_client_gate", check["office_client_gate"]),
        "standing_officials": "TURN_START_REUSED_OR_LAUNCHED",
        "turn_start_open_decree": open_decree.get("turn_start_open_decree"),
        "taizi_reawakened_from_closeout_idle": open_decree.get("taizi_reawakened_from_closeout_idle"),
        "three_departments_reawakened_from_closeout_idle": open_decree.get("three_departments_reawakened_from_closeout_idle"),
        "taizi_no_silence": True,
        "three_departments_no_silence": True,
        "no_silence_roles": list(NO_SILENCE_ROLES),
        "monitor_no_silence_roles": list(MONITOR_NO_SILENCE_ROLES),
        "supervision_channel": SUPERVISION_CHANNEL,
        "supervision_evidence": "PASSED",
        "silent_supervisor": "NOT_STARTED",
        "supercc_watchdog": "NOT_APPLICABLE",
        "watchdog_no_visible_window": True,
        "legacy_patrol_visible_pane": "disabled",
        "rate_limit_wake_hierarchy": RATE_LIMIT_WAKE_HIERARCHY,
        "supercc_request_limit_policy": SUPERCC_REQUEST_LIMIT_POLICY,
        "request_rate_limit_per_minute": SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE,
        "supercc_visible_core_roles": list(SUPERCC_VISIBLE_CORE_OFFICES),
        "turn_start_requested_roles": list(requested_roles),
        "turn_start_health_roles": list(health_roles),
        "non_visible_roles_observed_only": [role for role in requested_roles if role not in roles],
        "silent_supervisor_policy": SILENT_SUPERVISOR_POLICY,
        "six_ministry_step_plan_policy": SIX_MINISTRY_STEP_PLAN_POLICY,
        "check": check,
        "silent_supervisor": supervisor_status["silent_supervisor"],
        "supercc_watchdog": supervisor_status["supercc_watchdog"],
        "watchdog_no_visible_window": supervisor_status["watchdog_no_visible_window"],
        "watchdog_daemon_start": supervisor_status["watchdog_daemon_start"],
        "watchdog_daemon_stop": supervisor_status["watchdog_daemon_stop"],
        "legacy_patrol_visible_pane": supervisor_status["legacy_patrol_visible_pane"],
        "actions": actions,
    }


def restart_offices(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    roles = expand_office_selection(args.restart_offices or "all")
    check = supercc_check_for_args(args, workspace)
    actions: list[dict[str, Any]] = []
    if not check["passed"] and not args.force:
        return {
            "ok": False,
            "supercc_env_gate": check["supercc_env_gate"],
            "visible_display_gate": check["visible_display_gate"],
            "display_transport_gate": check["display_transport_gate"],
            "office_client_gate": check["office_client_gate"],
            "reason": "environment gate did not pass; use --force only for diagnostics",
            "check": check,
            "actions": actions,
        }
    visible = visible_office_panes(check)
    close_results: list[dict[str, Any]] = []
    current_pane = current_pane_id()
    zellij_session = current_zellij_session(check)
    for role in roles:
        for pane in visible.get(role, []):
            pane_id = pane.get("pane_id", "")
            if pane_id and pane_id != current_pane:
                close_results.append(
                    {
                        "role": role,
                        "pane_id": pane_id,
                        "result": close_pane(pane_id, args.dry_run, zellij_session=zellij_session),
                    }
                )
    actions.append({"close_visible_office_panes": close_results})
    agents_json = check["squad"].get("agents_json", [])
    active_ids = active_agent_ids(agents_json)
    archived: list[dict[str, Any]] = []
    for role in roles:
        if role in active_ids:
            archived.append({"role": role, "result": archive_agent(role, workspace, args.dry_run)})
    actions.append({"archive_restarted_squad_identities": archived})
    if not args.dry_run and close_results:
        time.sleep(1.0)
    launch = launch_offices(args, roles)
    actions.append({"relaunch_visible_offices": launch})
    post_restart_check = supercc_check_for_args(args, workspace)
    open_decree = mark_turn_start_open_decree(args, post_restart_check, native_wake=False)
    actions.append({"post_restart_open_decree_wake": open_decree})
    supervisor_status = {
        "ok": True,
        "silent_supervisor": "NOT_STARTED",
        "supercc_watchdog": "NOT_APPLICABLE",
        "watchdog_process": "NOT_APPLICABLE",
        "watchdog_no_visible_window": True,
        "watchdog_daemon_start": "NOT_APPLICABLE",
        "watchdog_daemon_stop": "NOT_APPLICABLE",
        "legacy_patrol_visible_pane": "disabled",
        "policy": SILENT_SUPERVISOR_POLICY,
    }
    actions.append({"post_restart_silent_supervisor_status": supervisor_status})
    return {
        "ok": bool(launch.get("ok")) and bool(open_decree.get("ok")) and bool(supervisor_status.get("ok")),
        "supercc_env_gate": launch.get("supercc_env_gate", check["supercc_env_gate"]),
        "visible_display_gate": launch.get("visible_display_gate", check["visible_display_gate"]),
        "display_transport_gate": launch.get("display_transport_gate", check["display_transport_gate"]),
        "office_client_gate": launch.get("office_client_gate", check["office_client_gate"]),
        "standing_officials": "RESTARTED",
        "roles": list(roles),
        "check": check,
        "turn_start_open_decree": open_decree.get("turn_start_open_decree"),
        "silent_supervisor": supervisor_status["silent_supervisor"],
        "supercc_watchdog": supervisor_status["supercc_watchdog"],
        "watchdog_no_visible_window": supervisor_status["watchdog_no_visible_window"],
        "watchdog_daemon_start": supervisor_status["watchdog_daemon_start"],
        "watchdog_daemon_stop": supervisor_status["watchdog_daemon_stop"],
        "legacy_patrol_visible_pane": supervisor_status["legacy_patrol_visible_pane"],
        "actions": actions,
    }


def closeout_silence(args: argparse.Namespace) -> dict[str, Any]:
    unfinished = parse_office_set(args.unfinished_offices)
    protected = INSPECTION_OFFICES if inspector_enabled(args) else ()
    return silence_roles(
        args,
        STATUS_OFFICES,
        unfinished=unfinished,
        reason="closeout_idle_receive_after_final_jiezhao",
        sender="taizi",
        protected_roles=protected,
        default_mode="idle_receive",
        protected_mode="awake_status_only",
        notify_inspector_expected_silence=inspector_enabled(args),
    )


def wake_offices(args: argparse.Namespace) -> dict[str, Any]:
    roles = expand_transport_office_selection(args.wake_offices)
    return wake_roles(args, roles, reason=args.wake_reason, sender=args.calling_office or "shangshu")


def watchdog_compat(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    script = Path(__file__).with_name(SUPERCC_WATCHDOG_SCRIPT)
    if not script.exists():
        return {
            "ok": False,
            "reason": "missing_supercc_watchdog_script",
            "watchdog_script": str(script),
            "legacy_patrol_disabled": True,
        }
    roles = str(args.patrol or "all")
    command = [
        sys.executable,
        str(script),
        "--workspace",
        str(workspace),
        "--roles",
        roles,
        "--format",
        "json",
    ]
    result = run_command(command, cwd=workspace, timeout=30, stdout_limit=60000, stderr_limit=12000)
    payload: dict[str, Any]
    try:
        payload = json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError as exc:
        payload = {"ok": False, "parse_error": str(exc), "stdout": result.get("stdout", "")}
    payload.update(
        {
            "ok": bool(result.get("ok")) and bool(payload.get("ok", False)),
            "legacy_patrol_disabled": True,
            "watchdog_script": str(script),
            "watchdog_command": command,
            "watchdog_process": {k: result.get(k) for k in ("ok", "returncode", "stderr", "error")},
        }
    )
    return payload


def super_entry(args: argparse.Namespace) -> dict[str, Any]:
    mode = str(args.super_entry or "turn-start").strip().lower()
    if mode == "check-only":
        mode = "check"
    workspace = Path(args.workspace).resolve()
    offices = args.super_entry_offices or "visible-core"
    roles = expand_office_selection(offices)
    launch_roles = tuple(role for role in roles if role not in INSPECTION_OFFICES)
    check = supercc_check_for_args(args, workspace)
    role_clients = check_office_clients_for_roles(args, workspace, launch_roles)
    plan = {
        "schema": SUPERCC_ENTRY_SCHEMA,
        "mode": mode,
        "requested_offices": offices,
        "resolved_roles": list(roles),
        "launch_roles": list(launch_roles),
        "skipped_legacy_inspection_roles": [role for role in roles if role in INSPECTION_OFFICES],
        "default_office_client": getattr(args, "office_client", None),
        "requested_office_client": getattr(args, "requested_office_client", None),
        "selection_source": getattr(args, "office_client_selection_source", None),
        "selection_signals": getattr(args, "office_client_selection_signals", []),
        "office_client_map": getattr(args, "office_client_map_resolved", {}),
        "office_clients_by_role": role_clients,
        "generic_cli_probe_required": any(office_client_for_role(args, role) == "cli" for role in launch_roles),
        "watchdog_script": SUPERCC_WATCHDOG_SCRIPT,
        "policy": SUPERCC_SUPER_ENTRY_POLICY,
    }
    if mode in {"plan", "check"}:
        return {
            "ok": bool(check.get("passed")) if mode == "check" else True,
            "supercc_env_gate": check.get("supercc_env_gate"),
            "visible_display_gate": check.get("visible_display_gate"),
            "display_transport_gate": check.get("display_transport_gate"),
            "office_client_gate": "PASSED" if role_clients.get("available") and check.get("office_client_gate") == "PASSED" else "runtime_degraded",
            "entry_plan": plan,
            "supercc_super_entry_policy": SUPERCC_SUPER_ENTRY_POLICY,
            "check": check,
        }
    if mode == "launch":
        result = launch_offices(args, launch_roles)
    elif mode == "turn-start":
        previous = getattr(args, "turn_start", None)
        args.turn_start = offices
        try:
            result = turn_start(args)
        finally:
            args.turn_start = previous
    elif mode == "restart":
        previous = getattr(args, "restart_offices", None)
        args.restart_offices = offices
        try:
            result = restart_offices(args)
        finally:
            args.restart_offices = previous
    else:
        raise ValueError(f"unknown --super-entry mode: {args.super_entry!r}")
    return {
        "ok": bool(result.get("ok")),
        "supercc_env_gate": result.get("supercc_env_gate", check.get("supercc_env_gate")),
        "visible_display_gate": result.get("visible_display_gate", check.get("visible_display_gate")),
        "display_transport_gate": result.get("display_transport_gate", check.get("display_transport_gate")),
        "office_client_gate": result.get("office_client_gate", check.get("office_client_gate")),
        "entry_plan": plan,
        "supercc_super_entry_policy": SUPERCC_SUPER_ENTRY_POLICY,
        "result": result,
    }


def noncurrent_inactive_cleanup_evaluator(
    workspace: Path,
    check: dict[str, Any],
    roles: tuple[str, ...],
    *,
    inactive_age_seconds: float,
    include_task_probe: bool,
) -> dict[str, Any]:
    agents_by_id = active_agents_by_id(check["squad"].get("agents_json", []))
    visible = visible_office_panes(check)
    current_session = current_zellij_session(check)
    candidates: list[dict[str, Any]] = []
    for role in roles:
        row = agents_by_id.get(role)
        panes = visible.get(role, [])
        response = simple_response_status(row, inactive_age_seconds=inactive_age_seconds)
        task_probe = role_task_snapshot(workspace, role) if include_task_probe else {"ok": None, "pending_or_acked_count": None, "reason": "not_probed"}
        unresolved_count = task_probe.get("pending_or_acked_count")
        no_unresolved_task = unresolved_count == 0 if isinstance(unresolved_count, int) else False
        task_probe_failed = task_probe.get("ok") is False
        noncurrent = row is not None and not panes
        inactive_or_stale = row is not None and not response["ok"]
        eligible = bool(noncurrent and inactive_or_stale and no_unresolved_task and not task_probe_failed)
        candidates.append(
            {
                "role": role,
                "agent_active": row is not None,
                "current_zellij_session": current_session,
                "visible_current_panes": panes,
                "noncurrent_session_or_not_visible": noncurrent,
                "inactive_or_stale": inactive_or_stale,
                "simple_response": response,
                "task_probe": task_probe,
                "no_unresolved_task": no_unresolved_task,
                "task_probe_failed": task_probe_failed,
                "eligible_for_non_destructive_squad_archive": eligible,
                "recommended_action": "squad_leave_archive" if eligible else ("manual_review_task_probe_failed" if task_probe_failed else "none"),
            }
        )
    eligible_roles = [row["role"] for row in candidates if row["eligible_for_non_destructive_squad_archive"]]
    return {
        "noncurrent_inactive_pane_cleanup": {
            "policy": "read-only evaluator by default; authorized applier may only use non-destructive squad archive, never zellij session deletion",
            "current_zellij_session": current_session,
            "inactive_age_seconds": inactive_age_seconds,
            "eligible_roles": eligible_roles,
            "candidates": candidates,
        }
    }


def role_task_snapshot(workspace: Path, role: str) -> dict[str, Any]:
    result = run_command(["squad", "task", "list", "--agent", role], cwd=workspace, timeout=8, stdout_limit=6000)
    text = result.get("stdout", "")
    pending_count = sum(1 for line in text.splitlines() if "queued" in line or "acked" in line)
    return {
        "ok": result.get("ok"),
        "pending_or_acked_count": pending_count,
        "stdout": text,
        "stderr": result.get("stderr", ""),
    }


def supercc_model_session_summary(check: dict[str, Any], roles: tuple[str, ...]) -> dict[str, Any]:
    active_ids = active_agent_ids(check.get("squad", {}).get("agents_json", []))
    visible = visible_office_panes(check)
    active_visible_roles = [
        role for role in roles if role in active_ids and visible.get(role)
    ]
    count = len(active_visible_roles)
    return {
        "supercc_model_session_count": count,
        "supercc_session_cap": SUPERCC_SESSION_CAP,
        "supercc_request_limit_policy": SUPERCC_REQUEST_LIMIT_POLICY,
        "request_rate_limit_per_minute": SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE,
        "active_visible_roles": active_visible_roles,
        "active_non_silent_window_count": count,
        "active_non_silent_window_cap": SUPERCC_SESSION_CAP,
        "active_non_silent_window_roles": active_visible_roles,
        "visible_active_office_count": count,
        "visible_active_office_cap": SUPERCC_SESSION_CAP,
        "over_cap": active_agent_count_over_cap(count),
        "over_active_non_silent_window_cap": active_agent_count_over_cap(count),
    }


RATE_LIMIT_SIGNAL_RE = re.compile(r"(?i)(?:\b429\b|rate[ _.-]?limit(?:ed|ing)?|too many requests)")
RATE_LIMIT_SIGNAL_KEYS = {
    "body",
    "detail",
    "details",
    "error",
    "errors",
    "exception",
    "last_error",
    "message",
    "messages",
    "mode",
    "raw",
    "reason",
    "reasons",
    "response",
    "result",
    "status",
    "stderr",
    "stdout",
    "summary",
    "traceback",
}
RATE_LIMIT_SKIP_KEY_FRAGMENTS = (
    "hash",
    "path",
    "source",
    "joined_at",
    "last_seen",
    "updated_at",
    "archived_at",
)


def rate_limit_signals(payload: Any) -> list[str]:
    signals: list[str] = []

    def add_matches(text: str) -> None:
        for match in RATE_LIMIT_SIGNAL_RE.finditer(text):
            signal = match.group(0)
            if signal not in signals:
                signals.append(signal)

    def scan(value: Any, *, key: str = "", force: bool = False) -> None:
        key_lower = key.lower()
        if key_lower and any(fragment in key_lower for fragment in RATE_LIMIT_SKIP_KEY_FRAGMENTS):
            return
        next_force = force or key_lower in RATE_LIMIT_SIGNAL_KEYS or "error" in key_lower or "stderr" in key_lower
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                scan(child_value, key=str(child_key), force=next_force)
            return
        if isinstance(value, (list, tuple, set)):
            for child_value in value:
                scan(child_value, key=key, force=next_force)
            return
        if isinstance(value, str):
            if next_force or not key_lower:
                add_matches(value)
            return
        if next_force and value is not None:
            add_matches(str(value))

    scan(payload)
    return sorted(signals)[:20]


def table_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "/").replace("\r", " ").replace("\n", " ").strip()


def csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    return '"' + text.replace('"', '""') + '"'



def default_dispatch_calling_office(role: str) -> str:
    return "shangshu" if role in MINISTRY_OFFICES else "taizi"


def resolved_calling_office(args: argparse.Namespace, role: str) -> str:
    explicit = getattr(args, "calling_office", None)
    return explicit.strip() if isinstance(explicit, str) and explicit.strip() else default_dispatch_calling_office(role)


def dispatch_target_profile_gate(role: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Prove the canonical target profile/dossier before transport probing."""

    fields = profile.get("profile_fields")
    fields = fields if isinstance(fields, dict) else {}
    profile_hash = profile.get("profile_hash")
    dossier_hash = sha256_file(office_dossier_path(role))
    reasons: list[str] = []
    if profile.get("office_profile_loaded") is not True:
        reasons.append("standing_profile_not_loaded")
    if fields.get("role_key") != role:
        reasons.append("standing_profile_role_mismatch")
    if fields.get("direct_superior") != fallback_direct_superior(role):
        reasons.append("standing_profile_direct_superior_mismatch")
    if not isinstance(profile_hash, str) or re.fullmatch(r"[0-9a-f]{64}", profile_hash) is None:
        reasons.append("standing_profile_hash_missing")
    if not isinstance(dossier_hash, str) or re.fullmatch(r"[0-9a-f]{64}", dossier_hash) is None:
        reasons.append("supercc_dossier_hash_missing")
    return {
        "ok": not reasons,
        "role": role,
        "profile_source": profile.get("profile_source"),
        "profile_hash": profile_hash,
        "office_dossier_path": str(office_dossier_path(role)),
        "office_dossier_hash": dossier_hash,
        "reason": "ok" if not reasons else ",".join(reasons),
        "reason_codes": reasons,
    }


def special_lifecycle_dispatch_authority(
    role: str,
    calling_office: str,
    superior: dict[str, str],
    profile: dict[str, Any],
    target_profile_gate: dict[str, Any],
) -> tuple[DispatchHierarchyDecision, dict[str, Any]]:
    """Resolve explicit special-role authority on top of the shared deny graph."""

    shared = validate_dispatch_hierarchy(
        action="dispatch",
        calling_office=calling_office,
        target_role=role,
        target_direct_superior=superior["direct_superior"],
        instance_kind="office",
        canonical_authority=True if target_profile_gate["ok"] else None,
        owner_role=None,
        child_profile=None,
    )
    manifest_path = skill_root() / "references" / "manifests" / "court-dispatch-hierarchy.v1.json"
    roles_path = skill_root() / "references" / "court-roles.yaml"
    action = SPECIAL_LIFECYCLE_ACTIONS.get(role)
    profile_fields = profile.get("profile_fields")
    profile_fields = profile_fields if isinstance(profile_fields, dict) else {}
    authority: dict[str, Any] = {
        "schema": "court.supercc.special_lifecycle_authority.v1",
        "role": role,
        "action": action,
        "calling_office": calling_office,
        "direct_superior": superior["direct_superior"],
        "allowed_callers": [],
        "hierarchy_manifest_path": str(manifest_path),
        "hierarchy_manifest_sha256": shared.hierarchy_manifest_sha256,
        "court_roles_path": str(roles_path),
        "court_roles_sha256": sha256_file(roles_path),
        "standing_profile_path": profile.get("profile_source"),
        "standing_profile_sha256": profile.get("profile_hash"),
        "court_roles_entry": "unknown",
        "gate": "FAILED",
    }
    if shared.reason_codes == ("dispatch_hierarchy_manifest_invalid",):
        authority["reason"] = "dispatch_hierarchy_manifest_invalid"
        return shared, authority
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        roles_text = roles_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        decision = DispatchHierarchyDecision(
            allowed=False,
            edge_class=None,
            normalized_caller=calling_office,
            normalized_target=role,
            normalized_owner=None,
            reason_codes=("dispatch_hierarchy_manifest_invalid",),
            hierarchy_schema=shared.hierarchy_schema,
            hierarchy_manifest_sha256=shared.hierarchy_manifest_sha256,
        )
        authority["reason"] = "dispatch_hierarchy_manifest_invalid"
        return decision, authority
    role_sets = manifest.get("role_sets") if isinstance(manifest, dict) else None
    special_roles = role_sets.get("special_lifecycle") if isinstance(role_sets, dict) else None
    canonical_roles = manifest.get("canonical_roles") if isinstance(manifest, dict) else None
    canonical_target = canonical_roles.get(role) if isinstance(canonical_roles, dict) else None
    manifest_superior = canonical_target.get("direct_superior") if isinstance(canonical_target, dict) else None
    authority["court_roles_entry"] = "present" if f"  {role}:" in roles_text else "absent_uses_manifest_and_profile"
    if (
        not isinstance(special_roles, list)
        or role not in special_roles
        or action is None
        or manifest_superior != superior["direct_superior"]
        or profile_fields.get("direct_superior") != manifest_superior
    ):
        decision = DispatchHierarchyDecision(
            allowed=False,
            edge_class=None,
            normalized_caller=calling_office,
            normalized_target=role,
            normalized_owner=None,
            reason_codes=("dispatch_hierarchy_manifest_invalid",),
            hierarchy_schema=shared.hierarchy_schema,
            hierarchy_manifest_sha256=shared.hierarchy_manifest_sha256,
        )
        authority["reason"] = "special_lifecycle_authority_mismatch"
        return decision, authority
    allowed_callers = tuple(
        part for part in str(manifest_superior).split("/") if part
    )
    authority["allowed_callers"] = list(allowed_callers)
    if not target_profile_gate["ok"]:
        authority["reason"] = "dispatch_hierarchy_target_profile_required"
        return shared, authority
    if calling_office not in allowed_callers:
        authority["reason"] = "dispatch_hierarchy_edge_forbidden"
        return shared, authority
    decision = DispatchHierarchyDecision(
        allowed=True,
        edge_class="special_lifecycle_dispatch",
        normalized_caller=calling_office,
        normalized_target=role,
        normalized_owner=None,
        reason_codes=(),
        hierarchy_schema=shared.hierarchy_schema,
        hierarchy_manifest_sha256=shared.hierarchy_manifest_sha256,
    )
    authority["gate"] = "PASSED"
    authority["reason"] = "ok"
    return decision, authority


def special_lifecycle_transport_preflight(
    args: argparse.Namespace,
    roles: tuple[str, ...] | list[str],
    *,
    transport_action: str,
    sender: str | None = None,
) -> dict[str, Any]:
    """Fail closed before any superCC environment or transport side effect."""

    entries: list[dict[str, Any]] = []
    for role in roles:
        if role not in SPECIAL_LIFECYCLE_OFFICES:
            continue
        profile = profile_metadata(role)
        profile_gate = dispatch_target_profile_gate(role, profile)
        superior = direct_superior_metadata(role)
        calling_office = sender or resolved_calling_office(args, role)
        decision, authority = special_lifecycle_dispatch_authority(
            role,
            calling_office,
            superior,
            profile,
            profile_gate,
        )
        entry = {
            "role": role,
            "transport_action": transport_action,
            "calling_office": calling_office,
            "direct_superior": superior["direct_superior"],
            "target_profile_gate": profile_gate,
            "special_lifecycle_action": SPECIAL_LIFECYCLE_ACTIONS[role],
            "special_lifecycle_authority": authority,
            "hierarchy_gate": "PASSED" if decision.allowed else "REJECTED",
            "hierarchy_schema": decision.hierarchy_schema,
            "hierarchy_manifest_sha256": decision.hierarchy_manifest_sha256,
            "hierarchy_edge_class": decision.edge_class,
            "hierarchy_calling_office": decision.normalized_caller,
            "hierarchy_target_role": decision.normalized_target,
            "hierarchy_owner_role": decision.normalized_owner,
        }
        entries.append(entry)
        if not decision.allowed:
            reason = (
                decision.reason_codes[0]
                if decision.reason_codes
                else "dispatch_hierarchy_edge_forbidden"
            )
            skipped = {"ok": False, "skipped": True, "reason": reason}
            return {
                "ok": False,
                "dispatch_blocked": True,
                "dispatch_block_reason": reason,
                "dispatch_hierarchy_reason": reason,
                "transport_action": transport_action,
                **entry,
                "special_lifecycle_preflight": entries,
                "task_evidence": dict(skipped),
                "squad_evidence": dict(skipped),
                "native_enter_dispatch": dict(skipped),
                "state": dict(skipped),
            }
    return {
        "ok": True,
        "transport_action": transport_action,
        "special_lifecycle_preflight": entries,
    }


def build_native_receive_command_prompt(
    role: str,
    *,
    action: str,
    dispatch_uid: str | None = None,
    task_id: str | None = None,
) -> str:
    commands = supercc_squad_relative_commands("receive", role, "--json")
    return commands["native"]


def build_dispatch_payload(
    args: argparse.Namespace,
    role: str,
    pane: dict[str, str] | None,
    profile: dict[str, Any],
    calling_office: str | None = None,
    hierarchy: DispatchHierarchyDecision | None = None,
) -> str:
    dispatch_uid = args.dispatch_uid or f"manual-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{role}"
    superior = direct_superior_metadata(role)
    calling_office = calling_office or resolved_calling_office(args, role)
    lines = [
        f"ENTER_DISPATCH dispatch_uid={dispatch_uid}",
        f"delivery_channel=NATIVE_DOUBLE_ENTER_VISIBLE_OR_NON_VISIBLE_STRUCTURED_TASK",
        f"assigned_office={role}",
        f"calling_office={calling_office}",
        f"calling_office_source={'explicit' if getattr(args, 'calling_office', None) else 'role_default'}",
        f"direct_superior={superior['direct_superior']}",
        f"direct_superior_source={superior['direct_superior_source']}",
        f"physical_enter_byte={PHYSICAL_ENTER_BYTE}",
        f"post_dispatch_physical_enter_delay_seconds={POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS:g}",
        f"squad_delivery_order={SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER}",
        f"native_enter_payload_kind={NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND}",
        f"physical_enter_sequence=squad_task_and_send_then_write_receive_command_then_enter_then_sleep_{POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS:g}s_then_enter",
        f"expected_pane_title={OFFICES[role]['title'] if role not in (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES) else ('NON_VISIBLE_MINISTRY_BY_CONTRACT' if role in MINISTRY_OFFICES else 'NON_VISIBLE_SPECIAL_LIFECYCLE_BY_CONTRACT')}",
        f"expected_pane_id={(pane or {}).get('pane_id', 'non_visible_structured_dispatch' if role in (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES) else 'missing')}",
        f"profile_source={profile['profile_source']}",
        f"profile_hash={profile.get('profile_hash') or 'missing'}",
        f"profile_version={profile.get('profile_version')}",
        f"office_dossier_path={office_dossier_path(role)}",
        f"office_dossier_hash={sha256_file(office_dossier_path(role)) or 'missing'}",
        f"light_bootstrap_policy={SUPERCC_LIGHT_BOOTSTRAP_POLICY}",
        f"six_ministry_step_plan_required={'true' if role in MINISTRY_OFFICES else 'false'}",
    ]
    if hierarchy is not None:
        lines.extend(
            [
                "hierarchy_gate=PASSED",
                f"hierarchy_schema={hierarchy.hierarchy_schema}",
                f"hierarchy_manifest_sha256={hierarchy.hierarchy_manifest_sha256}",
                f"hierarchy_edge_class={hierarchy.edge_class}",
                f"hierarchy_calling_office={hierarchy.normalized_caller}",
                f"hierarchy_target_role={hierarchy.normalized_target}",
                f"hierarchy_owner_role={hierarchy.normalized_owner or ''}",
            ]
        )
    if role in SPECIAL_LIFECYCLE_OFFICES:
        lines.extend(
            [
                f"special_lifecycle_action={SPECIAL_LIFECYCLE_ACTIONS[role]}",
                "special_lifecycle_visibility=non_visible_by_default",
            ]
        )
    lines.extend(["message:", args.message])
    return "\n".join(lines)


def enter_dispatch(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    role = args.role
    if role not in OFFICES:
        raise ValueError(f"unknown role for --enter-dispatch: {role}")
    if not args.message:
        raise ValueError("--enter-dispatch requires --message")

    profile = profile_metadata(role)
    target_profile_gate = dispatch_target_profile_gate(role, profile)
    superior = direct_superior_metadata(role)
    calling_office = resolved_calling_office(args, role)
    special_lifecycle_authority: dict[str, Any] | None = None
    if role in (*THREE_OFFICES, *MINISTRY_OFFICES):
        hierarchy = validate_dispatch_hierarchy(
            action="dispatch",
            calling_office=calling_office,
            target_role=role,
            target_direct_superior=superior["direct_superior"],
            instance_kind="office",
            canonical_authority=True if target_profile_gate["ok"] else None,
            owner_role=None,
            child_profile=None,
        )
    elif role in SPECIAL_LIFECYCLE_OFFICES:
        hierarchy, special_lifecycle_authority = special_lifecycle_dispatch_authority(
            role,
            calling_office,
            superior,
            profile,
            target_profile_gate,
        )
    else:
        hierarchy = None
    if hierarchy is not None and not hierarchy.allowed:
        reason = (
            hierarchy.reason_codes[0]
            if hierarchy.reason_codes
            else "dispatch_hierarchy_edge_forbidden"
        )
        skipped = {
            "ok": False,
            "skipped": True,
            "reason": reason,
        }
        return {
            "ok": False,
            "dispatch_uid": getattr(args, "dispatch_uid", None),
            "role": role,
            "calling_office": calling_office,
            "calling_office_source": (
                "explicit" if getattr(args, "calling_office", None) else "role_default"
            ),
            "direct_superior": superior["direct_superior"],
            "direct_superior_source": superior["direct_superior_source"],
            "target_profile_gate": target_profile_gate,
            "special_lifecycle_action": SPECIAL_LIFECYCLE_ACTIONS.get(role),
            "special_lifecycle_authority": special_lifecycle_authority,
            "dispatch_blocked": True,
            "dispatch_block_reason": reason,
            "dispatch_hierarchy_reason": reason,
            "hierarchy_gate": "REJECTED",
            "hierarchy_schema": hierarchy.hierarchy_schema,
            "hierarchy_manifest_sha256": hierarchy.hierarchy_manifest_sha256,
            "hierarchy_edge_class": hierarchy.edge_class,
            "hierarchy_calling_office": hierarchy.normalized_caller,
            "hierarchy_target_role": hierarchy.normalized_target,
            "hierarchy_owner_role": hierarchy.normalized_owner,
            "task_evidence": dict(skipped),
            "squad_evidence": dict(skipped),
            "native_enter_dispatch": dict(skipped),
            "state": dict(skipped),
        }
    hierarchy_evidence = (
        {
            "hierarchy_gate": "PASSED",
            "hierarchy_schema": hierarchy.hierarchy_schema,
            "hierarchy_manifest_sha256": hierarchy.hierarchy_manifest_sha256,
            "hierarchy_edge_class": hierarchy.edge_class,
            "hierarchy_calling_office": hierarchy.normalized_caller,
            "hierarchy_target_role": hierarchy.normalized_target,
            "hierarchy_owner_role": hierarchy.normalized_owner,
        }
        if hierarchy is not None
        else {
            "hierarchy_gate": "NOT_APPLICABLE_SPECIAL_LIFECYCLE",
            "hierarchy_schema": None,
            "hierarchy_manifest_sha256": None,
            "hierarchy_edge_class": None,
            "hierarchy_calling_office": calling_office,
            "hierarchy_target_role": role,
            "hierarchy_owner_role": None,
        }
    )
    special_lifecycle_evidence = {
        "special_lifecycle_action": SPECIAL_LIFECYCLE_ACTIONS.get(role),
        "special_lifecycle_authority": special_lifecycle_authority,
    }

    check = supercc_check_for_args(args, workspace)
    zellij_session = current_zellij_session(check)
    visible = visible_office_panes(check)
    uniqueness = office_uniqueness_gate(
        check,
        visible,
        role,
        require_visible=role not in (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES),
    )
    pane_selection = uniqueness["visible_pane_selection"]
    pane = pane_selection.get("pane") if pane_selection.get("ok") else None
    # Ministries and special lifecycle roles are non-visible by default under superCC.
    # Their dispatch may therefore be valid as a structured squad task even when no
    # visible pane or active canonical squad identity exists yet, provided there
    # are no duplicate visible panes or duplicate active identities for that role.
    active_ids_for_role = uniqueness.get("active_squad_ids_for_role") or []
    duplicate_ids_for_role = uniqueness.get("duplicate_identity_ids") or []
    visible_pane_count_for_role = int(uniqueness.get("visible_pane_count") or 0)
    non_visible_structured_dispatch = bool(
        role in (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES)
        and visible_pane_count_for_role == 0
        and len(active_ids_for_role) <= 1
        and not duplicate_ids_for_role
    )
    ministry_non_visible_dispatch = bool(
        role in MINISTRY_OFFICES and non_visible_structured_dispatch
    )
    special_lifecycle_non_visible_dispatch = bool(
        role in SPECIAL_LIFECYCLE_OFFICES and non_visible_structured_dispatch
    )
    payload_text = build_dispatch_payload(
        args,
        role,
        pane,
        profile,
        calling_office,
        hierarchy,
    )
    dispatch_uid = args.dispatch_uid or payload_text.splitlines()[0].split("=", 1)[1]
    native_commands: list[list[str]] = []
    native_enter_dispatch: dict[str, Any]
    delivery_channel = "NATIVE_DOUBLE_ENTER_VISIBLE"
    dispatch_blocked = False
    dispatch_block_reason: str | None = None
    if not uniqueness.get("ok") and not non_visible_structured_dispatch:
        dispatch_blocked = True
        dispatch_block_reason = uniqueness.get("reason") or "office_uniqueness_gate_failed"
        delivery_channel = "FAILED_OFFICE_UNIQUENESS_GATE"
        native_enter_dispatch = {
            "ok": False,
            "reason": dispatch_block_reason,
            "commands": [],
            "visible_pane_selection": pane_selection,
            "office_uniqueness_gate": uniqueness,
        }
    elif ministry_non_visible_dispatch:
        delivery_channel = NON_VISIBLE_MINISTRY_DISPATCH_CHANNEL
        native_enter_dispatch = {
            "ok": False,
            "skipped": True,
            "reason": "ministry_non_visible_by_contract; structured squad task plus shangshu supervision is the dispatch channel",
            "commands": [],
            "visible_pane_selection": pane_selection,
            "office_uniqueness_gate": uniqueness,
            "visible_window_contract": "six_ministries_must_not_be_visible_by_default",
            "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER,
        }
    elif special_lifecycle_non_visible_dispatch:
        delivery_channel = NON_VISIBLE_SPECIAL_LIFECYCLE_DISPATCH_CHANNEL
        native_enter_dispatch = {
            "ok": False,
            "skipped": True,
            "reason": "special_lifecycle_non_visible_by_contract; structured squad task plus direct-superior review is the dispatch channel",
            "commands": [],
            "visible_pane_selection": pane_selection,
            "office_uniqueness_gate": uniqueness,
            "visible_window_contract": "special_lifecycle_roles_must_not_be_visible_by_default",
            "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER,
        }
    elif not pane:
        if not getattr(args, "allow_squad_only_fallback", False):
            dispatch_blocked = True
            dispatch_block_reason = "expected_visible_pane_missing_and_squad_only_fallback_not_allowed"
            delivery_channel = "FAILED_VISIBLE_PANE_GATE"
            native_enter_dispatch = {
                "ok": False,
                "reason": dispatch_block_reason,
                "commands": [],
                "visible_pane_selection": pane_selection,
                "office_uniqueness_gate": uniqueness,
            }
        else:
            delivery_channel = "SQUAD_ONLY_FALLBACK_DEGRADED"
            native_enter_dispatch = {
                "ok": False,
                "reason": "expected visible pane missing; explicit --allow-squad-only-fallback used",
                "commands": [],
                "visible_pane_selection": pane_selection,
                "office_uniqueness_gate": uniqueness,
            }
    squad_message = f"[ENTER_DISPATCH_MIRROR] dispatch_uid={dispatch_uid}; delivery_channel={delivery_channel}\n{payload_text}"
    task_title = getattr(args, "task_title", None) or f"ENTER_DISPATCH {dispatch_uid} -> {role}"
    task_required = not dispatch_blocked
    if args.dry_run:
        task_evidence = create_squad_task_assignment(
            workspace,
            calling_office,
            role,
            title=task_title,
            body=payload_text,
            dispatch_uid=dispatch_uid,
            dry_run=True,
        ) if task_required else {"ok": False, "skipped": True, "reason": dispatch_block_reason}
        squad_command = ["squad", "send"]
        if task_evidence.get("task_id"):
            squad_command.extend(["--task-id", str(task_evidence["task_id"])])
        squad_command.extend([calling_office, role, squad_message])
        if task_required and not isinstance(task_evidence.get("task_id"), str):
            squad_evidence = {
                "ok": False,
                "dry_run": True,
                "skipped": True,
                "reason": "task_id_parse_failed_before_squad_mirror",
                "command": squad_command,
                "task_id": task_evidence.get("task_id"),
            }
        else:
            squad_evidence = {"ok": task_required, "dry_run": True, "command": squad_command, "task_id": task_evidence.get("task_id")}
    elif task_required:
        task_evidence = create_squad_task_assignment(
            workspace,
            calling_office,
            role,
            title=task_title,
            body=payload_text,
            dispatch_uid=dispatch_uid,
            dry_run=False,
        )
        task_id = task_evidence.get("task_id")
        if not bool(task_evidence.get("ok")):
            squad_evidence = {
                "ok": False,
                "skipped": True,
                "reason": "task_create_failed_before_squad_mirror",
                "task_id": task_id,
            }
        elif not isinstance(task_id, str):
            squad_evidence = {
                "ok": False,
                "skipped": True,
                "reason": "task_id_parse_failed_before_squad_mirror",
                "task_id": task_id,
                "task_id_parse_ok": False,
            }
        else:
            squad_evidence = send_squad_notice(workspace, calling_office, role, squad_message, dry_run=False, task_id=task_id)
    else:
        task_evidence = {"ok": False, "skipped": True, "reason": dispatch_block_reason}
        squad_evidence = {"ok": False, "skipped": True, "reason": dispatch_block_reason}

    task_id_for_cc = task_evidence.get("task_id") if isinstance(task_evidence.get("task_id"), str) else None
    squad_delivery_ok = (not task_required) or (bool(task_evidence.get("ok")) and bool(task_id_for_cc) and bool(squad_evidence.get("ok")))
    if not dispatch_blocked and pane:
        pane_id = pane["pane_id"]
        command_prompt = build_native_receive_command_prompt(
            role,
            action="enter_dispatch",
            dispatch_uid=dispatch_uid,
            task_id=task_id_for_cc,
        )
        native_commands = [
            zellij_command_args("action", "write-chars", "-p", pane_id, command_prompt, session=zellij_session),
            zellij_command_args("action", "write", "-p", pane_id, PHYSICAL_ENTER_BYTE, session=zellij_session),
            ["sleep", f"{POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS:g}s"],
            zellij_command_args("action", "write", "-p", pane_id, PHYSICAL_ENTER_BYTE, session=zellij_session),
        ]
        if not squad_delivery_ok:
            native_enter_dispatch = {
                "ok": False,
                "skipped": True,
                "reason": "squad_delivery_failed_before_native_enter",
                "commands": native_commands,
                "native_enter_payload_kind": NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND,
                "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER,
                "physical_enter_byte": PHYSICAL_ENTER_BYTE,
                "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
                "task_evidence": task_evidence,
                "squad_evidence": squad_evidence,
            }
        elif args.dry_run:
            native_enter_dispatch = {
                "ok": True,
                "dry_run": True,
                "commands": native_commands,
                "native_enter_payload_kind": NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND,
                "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER,
                "physical_enter_byte": PHYSICAL_ENTER_BYTE,
                "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
                "post_dispatch_physical_enter": "planned",
            }
        else:
            write_result = run_command(native_commands[0], cwd=workspace, timeout=10, stdout_limit=4000, stderr_limit=4000)
            enter_result = run_command(native_commands[1], cwd=workspace, timeout=10, stdout_limit=4000, stderr_limit=4000)
            time.sleep(max(0.0, POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS))
            post_enter_result = run_command(native_commands[3], cwd=workspace, timeout=10, stdout_limit=4000, stderr_limit=4000)
            native_enter_dispatch = {
                "ok": bool(write_result.get("ok")) and bool(enter_result.get("ok")) and bool(post_enter_result.get("ok")),
                "write": write_result,
                "enter": enter_result,
                "commands": native_commands,
                "native_enter_payload_kind": NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND,
                "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER,
                "physical_enter_byte": PHYSICAL_ENTER_BYTE,
                "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
                "post_dispatch_physical_enter": post_enter_result,
            }
    phase_cycle = supercc_phase_for_roles((role,), sender=calling_office)
    inspector_wake_cc = maybe_send_inspector_wake_cc(
        args,
        workspace,
        calling_office,
        (role,),
        reason="enter_dispatch",
        expected_mode="task_queued_non_visible" if ministry_non_visible_dispatch else "awake",
        dispatch_uid=dispatch_uid,
        task_id=task_id_for_cc,
    )

    state_mode = "runtime_degraded" if dispatch_blocked else ("task_queued_non_visible" if non_visible_structured_dispatch else "awake")
    state_reason = f"enter_dispatch_blocked:{dispatch_block_reason}" if dispatch_blocked else ("enter_dispatch_non_visible_structured_task" if non_visible_structured_dispatch else "enter_dispatch")
    native_enter_role = "not_used_non_visible_structured_dispatch" if non_visible_structured_dispatch else "receive_command_wake_after_squad_task_and_send"
    dispatch_route_policy = (
        [delivery_channel]
        if non_visible_structured_dispatch
        else ["SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER", "NATIVE_DOUBLE_ENTER_VISIBLE receive-command wake", "HERMES_PROFILE_NATIVE_READINESS_SUPPLEMENT if Hermes"]
    )
    dispatch_ok = (not dispatch_blocked) and (
        squad_delivery_ok
        if non_visible_structured_dispatch or delivery_channel.startswith("SQUAD_ONLY")
        else (squad_delivery_ok and bool(native_enter_dispatch.get("ok")))
    )
    state = {"ok": True, "skipped": True, "reason": "dry-run"} if args.dry_run else write_office_state(
        workspace,
        {
            role: {
                **build_mode_records((role,), default_mode=state_mode, reason=state_reason)[role],
                "dispatch_uid": dispatch_uid,
                "office_uniqueness_gate": uniqueness,
                "dispatch_delivery_channel": delivery_channel,
                "dispatch_router_phase": "phase2_structured_task_required_non_visible_ministry_supported",
                "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER if not dispatch_blocked else None,
                "native_enter_payload_kind": NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND if pane else None,
                "ministry_non_visible_dispatch": ministry_non_visible_dispatch,
                "special_lifecycle_non_visible_dispatch": special_lifecycle_non_visible_dispatch,
                "non_visible_structured_dispatch": non_visible_structured_dispatch,
                "visible_window_contract": "visible_windows_only_taizi_three_departments; six_ministries_and_special_lifecycle_roles_non_visible_by_default",
                "supercc_phase_cycle": phase_cycle,
                "inspector_wake_cc_policy": INSPECTOR_WAKE_CC_POLICY,
                "inspector_wake_cc": inspector_wake_cc,
                "wake_cc_to_patrol_inspector": inspector_enabled(args),
                "supervision_channel": SUPERVISION_CHANNEL,
                "supervision_evidence": "PASSED",
                "shangshu_ministry_report_integration": "REQUIRED",
                "squad_active_wake_capability": "not_guaranteed_probe_20260629_stale_agent_remained_queued_unleased",
                "squad_role": "structured_task_and_audit_mirror_not_sole_wake",
                "native_enter_role": native_enter_role,
                "hermes_profile_native_policy": "supplemental_readiness_only_for_Hermes; normal_superCC_requires_zellij_squad_visible_route; readiness_only_is_not_dispatch_success",
                "calling_office": calling_office,
                "calling_office_source": "explicit" if args.calling_office else "role_default",
                "direct_superior": superior["direct_superior"],
                "direct_superior_source": superior["direct_superior_source"],
                "target_profile_gate": target_profile_gate,
                **hierarchy_evidence,
                **special_lifecycle_evidence,
                "native_enter_dispatch": native_enter_dispatch,
                "physical_enter_byte": PHYSICAL_ENTER_BYTE,
                "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
                "task_evidence": task_evidence,
                "squad_evidence": squad_evidence,
                "expected_pane_title": OFFICES[role]["title"],
                "expected_pane_id": (pane or {}).get("pane_id"),
            }
        },
        zellij_session=current_zellij_session(check),
        dry_run=False,
    )

    return {
        "ok": dispatch_ok,
        "dispatch_uid": dispatch_uid,
        "role": role,
        "calling_office": calling_office,
        "calling_office_source": "explicit" if args.calling_office else "role_default",
        "direct_superior": superior["direct_superior"],
        "direct_superior_source": superior["direct_superior_source"],
        "target_profile_gate": target_profile_gate,
        **hierarchy_evidence,
        **special_lifecycle_evidence,
        "office_uniqueness_gate": uniqueness,
        "dispatch_blocked": dispatch_blocked,
        "dispatch_block_reason": dispatch_block_reason,
        "dispatch_delivery_channel": delivery_channel,
        "dispatch_router_phase": "phase2_structured_task_required_non_visible_ministry_supported",
        "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER if not dispatch_blocked else None,
        "native_enter_payload_kind": NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND if pane else None,
        "ministry_non_visible_dispatch": ministry_non_visible_dispatch,
        "special_lifecycle_non_visible_dispatch": special_lifecycle_non_visible_dispatch,
        "non_visible_structured_dispatch": non_visible_structured_dispatch,
        "visible_window_contract": "visible_windows_only_taizi_three_departments; six_ministries_and_special_lifecycle_roles_non_visible_by_default",
        "supercc_phase_cycle": phase_cycle,
        "supercc_request_limit_policy": SUPERCC_REQUEST_LIMIT_POLICY,
        "request_rate_limit_per_minute": SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE,
        "inspector_wake_cc_policy": INSPECTOR_WAKE_CC_POLICY,
        "inspector_wake_cc": inspector_wake_cc,
        "wake_cc_to_patrol_inspector": inspector_enabled(args),
        "supervision_channel": SUPERVISION_CHANNEL,
        "supervision_evidence": "PASSED",
        "shangshu_ministry_report_integration": "REQUIRED",
        "squad_active_wake_capability": "not_guaranteed_probe_20260629_stale_agent_remained_queued_unleased",
        "squad_role": "structured_task_and_audit_mirror_not_sole_wake",
        "native_enter_role": native_enter_role,
        "hermes_profile_native_policy": "supplemental_readiness_only_for_Hermes; normal_superCC_requires_zellij_squad_visible_route; readiness_only_is_not_dispatch_success",
        "dispatch_route_policy_phase1": dispatch_route_policy,
        "expected_pane_title": (
            "NON_VISIBLE_MINISTRY_BY_CONTRACT"
            if ministry_non_visible_dispatch
            else (
                "NON_VISIBLE_SPECIAL_LIFECYCLE_BY_CONTRACT"
                if special_lifecycle_non_visible_dispatch
                else OFFICES[role]["title"]
            )
        ),
        "expected_pane_id": None if non_visible_structured_dispatch else (pane or {}).get("pane_id"),
        "office_profile_loaded": profile["office_profile_loaded"],
        "profile_source": profile["profile_source"],
        "profile_hash": profile["profile_hash"],
        "profile_version": profile["profile_version"],
        "office_dossier_path": str(office_dossier_path(role)),
        "office_dossier_hash": sha256_file(office_dossier_path(role)),
        "light_bootstrap_policy": SUPERCC_LIGHT_BOOTSTRAP_POLICY,
        "native_enter_dispatch": native_enter_dispatch,
        "physical_enter_byte": PHYSICAL_ENTER_BYTE,
        "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
        "task_evidence": task_evidence,
        "squad_evidence": squad_evidence,
        "state": state,
        "supercc_env_gate": check.get("supercc_env_gate"),
        "visible_display_gate": check.get("visible_display_gate"),
        "display_transport_gate": check.get("display_transport_gate"),
        "office_client_gate": check.get("office_client_gate"),
        "check": check,
    }


def dispatch_router_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    """Phase-2 fast router proof: compute channel order and evidence without dispatch side effects."""
    workspace = Path(args.workspace).resolve()
    role = args.role
    if role not in OFFICES:
        raise ValueError(f"unknown role for --dispatch-router-dry-run: {role}")
    if not args.message:
        raise ValueError("--dispatch-router-dry-run requires --message")

    source_agent_label = (getattr(args, "source_agent_label", None) or "Hermes").strip()
    runtime_client = getattr(args, "runtime_client", None) or getattr(args, "office_client", "hermescli")
    is_hermes_source = source_agent_label.lower() == "hermes" or runtime_client in {"hermescli", "hermes_desktop_readiness"}
    fast_switch_timeout_seconds = float(getattr(args, "router_fast_switch_timeout_seconds", 3.0) or 3.0)

    hermes_native = {
        "enabled": is_hermes_source,
        "attempted": is_hermes_source,
        "dry_run": True,
        "channel": "HERMES_PROFILE_NATIVE_READINESS_SUPPLEMENT_DRY_RUN",
        "timeout_seconds": fast_switch_timeout_seconds,
        "readiness_only": True,
        "dispatch_executed": False,
        "reason": "source_agent_label_is_Hermes" if is_hermes_source else "skipped_non_hermes_source_agent",
    }
    if is_hermes_source:
        hermes_cmd = [sys.executable, str(Path(__file__).with_name("ensure_hermes_supercc.py")), "--surface", "cli", "--format", "json"]
        probe = run_command(hermes_cmd, cwd=workspace, timeout=max(5, int(fast_switch_timeout_seconds) + 3), stdout_limit=12000, stderr_limit=4000)
        hermes_native["readiness_probe_command"] = hermes_cmd
        hermes_native["readiness_probe_ok"] = bool(probe.get("ok"))
        hermes_native["readiness_probe_returncode"] = probe.get("returncode")
        hermes_native["readiness_probe_error"] = probe.get("error")
        try:
            readiness_payload = json.loads(probe.get("stdout") or "{}") if probe.get("ok") else {}
        except json.JSONDecodeError as exc:
            readiness_payload = {"parse_error": str(exc)}
        hermes_native["readiness_payload_summary"] = {
            key: readiness_payload.get(key)
            for key in (
                "ok",
                "source_agent_label",
                "runtime_client",
                "hermes_surface",
                "hermes_profile_readiness_evidence",
                "profile_native_evidence_scope",
            )
        }
        hermes_native["selected_as_semantic_first"] = False
        hermes_native["phase2_policy"] = "readiness_only_supplement; normal_superCC_requires_zellij_squad_visible_route"

    enter_args = argparse.Namespace(**vars(args))
    enter_args.enter_dispatch = True
    enter_args.dispatch_router_dry_run = False
    enter_args.dry_run = True
    enter_result = enter_dispatch(enter_args)

    non_visible_ministry = bool(enter_result.get("ministry_non_visible_dispatch"))
    non_visible_special = bool(enter_result.get("special_lifecycle_non_visible_dispatch"))
    non_visible_structured = non_visible_ministry or non_visible_special
    non_visible_channel = (
        NON_VISIBLE_MINISTRY_DISPATCH_CHANNEL
        if non_visible_ministry
        else NON_VISIBLE_SPECIAL_LIFECYCLE_DISPATCH_CHANNEL
    )
    route_order = (
        [non_visible_channel]
        if non_visible_structured
        else (
            ["SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER_DRY_RUN", "NATIVE_DOUBLE_ENTER_VISIBLE_RECEIVE_COMMAND_DRY_RUN", "HERMES_PROFILE_NATIVE_READINESS_SUPPLEMENT_DRY_RUN"]
            if is_hermes_source
            else ["SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER_DRY_RUN", "NATIVE_DOUBLE_ENTER_VISIBLE_RECEIVE_COMMAND_DRY_RUN"]
        )
    )
    native_ok = bool((enter_result.get("native_enter_dispatch") or {}).get("ok"))
    hermes_ready = bool(hermes_native.get("readiness_probe_ok")) if is_hermes_source else False
    selected_primary_wake_channel = non_visible_channel if non_visible_structured else "NATIVE_DOUBLE_ENTER_VISIBLE_DRY_RUN"
    if is_hermes_source and not hermes_ready:
        hermes_native["fast_fallback_triggered"] = True
        hermes_native["fallback_reason"] = "HERMES_PROFILE_NATIVE_SUPPLEMENT_TIMEOUT_OR_UNREADY"
    return {
        "ok": bool(enter_result.get("ok")) if non_visible_structured else native_ok,
        "dispatch_router_phase": "phase2_dry_run_fast_route_selection",
        "source_agent_label": source_agent_label,
        "runtime_client": runtime_client,
        "role": role,
        "dispatch_uid": enter_result.get("dispatch_uid"),
        "route_order": route_order,
        "selected_primary_wake_channel": selected_primary_wake_channel,
        "non_visible_ministry_dispatch": non_visible_ministry,
        "non_visible_special_lifecycle_dispatch": non_visible_special,
        "hermes_profile_native": hermes_native,
        "native_double_enter": {
            "enabled": not non_visible_structured,
            "role": "receive_command_wake_after_squad_task_and_send_for_visible_offices",
            "dry_run": True,
            "ok": bool((enter_result.get("native_enter_dispatch") or {}).get("ok")),
            "skipped": non_visible_ministry,
            "reason": "non_visible_ministry_uses_structured_task_audit_mirror" if non_visible_ministry else None,
            "native_enter_payload_kind": (enter_result.get("native_enter_dispatch") or {}).get("native_enter_payload_kind"),
            "squad_delivery_order": (enter_result.get("native_enter_dispatch") or {}).get("squad_delivery_order"),
            "physical_enter_byte": enter_result.get("physical_enter_byte"),
            "post_dispatch_physical_enter_delay_seconds": enter_result.get("post_dispatch_physical_enter_delay_seconds"),
            "commands": (enter_result.get("native_enter_dispatch") or {}).get("commands", []),
        },
        "squad_mirror": {
            "enabled": True,
            "role": "structured_task_and_audit_mirror_not_guaranteed_active_wake",
            "dry_run": True,
            "squad_active_wake_capability": enter_result.get("squad_active_wake_capability"),
            "task_evidence": enter_result.get("task_evidence"),
            "squad_evidence": enter_result.get("squad_evidence"),
        },
        "fast_switch_policy": {
            "timeout_seconds": fast_switch_timeout_seconds,
            "no_retry_dead_loop": True,
            "fallback_order": route_order[1:] if is_hermes_source else route_order,
        },
        "cap_policy": {
            "active_non_silent_window_cap": SUPERCC_SESSION_CAP,
            "operator": "<=",
            "count_source": "patrol.active_non_silent_window_count",
        },
        "visible_display_required": True,
        "enter_result_summary": {k: enter_result.get(k) for k in ("ok", "dispatch_delivery_channel", "dispatch_router_phase", "visible_display_gate", "office_client_gate", "supercc_env_gate")},
        "enter_result": enter_result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        default=str(user_home()),
        help="Workspace passed to superCC office panes. Defaults to the current user's home directory.",
    )
    parser.add_argument("--check-only", action="store_true", help="Only check zellij/squad visible display and selected office-client readiness.")
    parser.add_argument("--super-entry", nargs="?", const="turn-start", choices=("plan", "check", "check-only", "launch", "turn-start", "restart"), help="Unified superCC entry: resolve current/source CLI or per-office mappings, then plan/check/launch/turn-start/restart through structured gates.")
    parser.add_argument("--super-entry-offices", default="visible-core", help="Office selection for --super-entry. Accepts role keys and aliases such as visible-core, three, ministries, all.")
    parser.add_argument("--write-agent-dossiers", action="store_true", help="Write/refresh per-office superCC AGENTS.md dossiers without launching model sessions.")
    parser.add_argument("--launch-three", action="store_true", help="Launch standing 三省 visible panes with the selected office client.")
    parser.add_argument("--launch-visible-core", action="store_true", help="Launch the superCC visible core: 三省; 太子 is the current pane.")
    parser.add_argument(
        "--launch-offices",
        help="Launch visible zellij panes for offices. Use 'visible-core', 'three', 'ministries', 'all', or comma-separated role keys.",
    )
    parser.add_argument(
        "--turn-start",
        nargs="?",
        const="visible-core",
        help="At each superCC turn start, inspect known offices, release noncurrent inactive ids, ensure 三省 visible core offices, and keep 六部 non-visible/silent unless 尚书省 dispatches a step.",
    )
    parser.add_argument(
        "--restart-offices",
        nargs="?",
        const="visible-core",
        help="Close current visible office panes, archive their squad ids, then relaunch them. Defaults to 三省; use inspection/patrol only for explicit diagnostics.",
    )
    parser.add_argument("--closeout-silence", action="store_true", help="After final 结诏, mark resolved agente idle_receive except any --unfinished-offices; mirror expected silence to patrol only when --enable-inspector is set.")
    parser.add_argument("--wake-offices", help="Wake selected offices, normally by 尚书省 dispatch. Use role keys, 'ministries', or comma-separated roles.")
    parser.add_argument("--patrol", nargs="?", const="all", help="Compatibility alias for script watchdog status. Visible monitor publish/refresh is disabled.")
    parser.add_argument("--enable-inspector", action="store_true", help="Deprecated compatibility flag; routine superCC uses hierarchy plus scripts/supercc_watchdog.py instead of a visible monitor pane.")
    parser.add_argument("--skip-inspector", action="store_true", help="Force-disable legacy 监察 compatibility paths.")
    parser.add_argument("--no-publish-patrol-pane", action="store_true", help="Deprecated compatibility flag; watchdog status is script output and never publishes to a visible monitor pane.")
    parser.add_argument("--skip-patrol-self-receive", action="store_true", help="Deprecated compatibility flag retained for old invocations.")
    parser.add_argument("--skip-patrol-state-update", action="store_true", help="Deprecated compatibility flag retained for old invocations.")
    parser.add_argument("--skip-self-check-before-display", action="store_true", help="Deprecated compatibility flag retained for old invocations.")
    parser.add_argument("--enter-dispatch", action="store_true", help="Queue squad task/send first, then native-enter the office receive command with one delayed physical Enter; use --dry-run to print evidence only.")
    parser.add_argument("--dispatch-router-dry-run", action="store_true", help="Phase-2 dry-run router: queue the squad task/audit mirror before the native double-Enter receive-command wake; Hermes profile readiness is supplemental only.")
    parser.add_argument("--source-agent-label", default="Hermes", help="Source agent label for --dispatch-router-dry-run, e.g. Hermes or Codex.")
    parser.add_argument("--runtime-client", choices=("codex", "hermescli", "hermes_desktop_readiness", "claude", "cli"), help="Runtime client hint for --dispatch-router-dry-run. Hermes desktop is readiness-only unless zellij+squad is also proven.")
    parser.add_argument("--router-fast-switch-timeout-seconds", type=float, default=3.0, help="Fast-switch timeout for phase-2 dispatch-router dry-run probes.")
    parser.add_argument("--role", help="Role key for --enter-dispatch or --dispatch-router-dry-run.")
    parser.add_argument("--message", help="Bounded dispatch message for --enter-dispatch.")
    parser.add_argument("--dispatch-uid", help="Stable dispatch uid for ENTER_DISPATCH and squad mirror evidence.")
    parser.add_argument("--task-title", help="Structured squad task title for --enter-dispatch. Defaults to ENTER_DISPATCH <uid> -> <role>.")
    parser.add_argument("--allow-squad-only-fallback", action="store_true", help="Explicitly allow SQUAD_ONLY_FALLBACK_DEGRADED when the role is unique but has no current visible pane.")
    parser.add_argument("--include-pending-tasks", action="store_true", help="For --patrol, include read-only squad task list snapshots per role.")
    parser.add_argument("--rename-taizi", action="store_true", help="Rename and squad-join the current pane as 太子.")
    parser.add_argument("--office-client", default=os.environ.get("COURT_OFFICE_CLIENT", "auto"), help=f"Runtime client launched in office panes. Built-ins: {', '.join(OFFICE_CLIENT_CHOICES)}; any other value is treated as a generic CLI command and probed.")
    parser.add_argument("--hermescli-command", default=os.environ.get("COURT_HERMESCLI_COMMAND", "hermes"), help="Hermes CLI executable used when --office-client hermescli.")
    parser.add_argument("--claude-command", default=os.environ.get("COURT_CLAUDE_COMMAND", "claude"), help="Claude Code executable used when --office-client claude.")
    parser.add_argument("--office-client-command", default=os.environ.get("COURT_OFFICE_CLIENT_COMMAND") or os.environ.get("COURT_SOURCE_CLI_COMMAND"), help="Executable used when --office-client cli, or when auto is driven by COURT_OFFICE_CLIENT_COMMAND/COURT_SOURCE_CLI_COMMAND.")
    parser.add_argument("--office-client-arg", action="append", default=[], help="Append one argument for --office-client cli. Repeat for multiple args; the prompt is added separately according to --office-client-prompt-mode.")
    parser.add_argument("--office-client-args", default=os.environ.get("COURT_OFFICE_CLIENT_ARGS"), help="Shell-style extra argument string for --office-client cli.")
    parser.add_argument("--office-client-prompt-mode", choices=("argument", "stdin"), default=os.environ.get("COURT_OFFICE_CLIENT_PROMPT_MODE", "argument"), help="How a generic --office-client cli receives the office prompt.")
    parser.add_argument("--office-client-map", action="append", default=[], help="Per-office client mapping. Repeat or comma-separate role=client entries, e.g. three=claude,hubu=cli,gongbu=codex.")
    parser.add_argument("--office-client-command-map", action="append", default=[], help="Per-office executable mapping for roles using client=cli, e.g. gongbu=/path/to/tool.")
    parser.add_argument("--office-client-args-map", action="append", default=[], help="Per-office extra CLI args mapping for roles using client=cli, e.g. gongbu='--flag value'.")
    parser.add_argument("--office-client-prompt-mode-map", action="append", default=[], help="Per-office generic CLI prompt mode mapping, e.g. gongbu=stdin.")
    parser.add_argument("--zellij-session", default=os.environ.get("COURT_ZELLIJ_SESSION"), help="Target zellij session for superCC pane actions. Defaults to the current session, or the newest active session containing the Taizi pane.")
    parser.add_argument("--ministry-mode", choices=("silent", "awake"), default="silent", help="Default 六部 mode after launch; superCC uses silent unless 尚书省 dispatches work.")
    parser.add_argument("--inactive-age-seconds", type=float, default=3600.0, help="Age threshold for releasing active squad ids that are not visible in the current zellij workspace.")
    parser.add_argument("--unfinished-offices", help="Comma/space-separated roles that remain awake during --closeout-silence.")
    parser.add_argument("--calling-office", help="Sender squad id. Defaults to shangshu for --wake-offices/六部 dispatch and taizi for 三省/监察/史馆 --enter-dispatch.")
    parser.add_argument("--wake-reason", default="shangshu_dispatch", help="Reason written and sent with --wake-offices.")
    parser.add_argument("--reclaim-existing", action="store_true", help="Archive active canonical squad ids before rejoining them.")
    parser.add_argument("--archive-test-agents", action="store_true", help="Archive known stale smoke-test squad ids.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without changing panes or squad state.")
    parser.add_argument("--force", action="store_true", help="Allow launch diagnostics even if the environment gate fails.")
    parser.add_argument("--dangerous-yolo", action="store_true", help="Use Codex dangerous no-sandbox for child panes. Requires explicit user approval.")
    parser.add_argument("--no-auto-install-deps", action="store_true", help="Do not auto-bootstrap missing zellij/squad dependencies.")
    parser.add_argument("--allow-unverified-release-asset", action="store_true", help="Pass through to the portable bootstrap when a GitHub release asset lacks a checksum.")
    parser.add_argument("--court-code", help="Optional Shiguan court code to include in child prompts.")
    parser.add_argument("--office-show-delay", type=float, help="Presentation-only seconds between adjacent visible office starts. Default: 1; hard range: 0-5.")
    parser.add_argument("--launch-delay", type=float, help="Deprecated compatibility alias for --office-show-delay.")
    parser.add_argument("--codex-start-cooldown", type=float, help="Deprecated compatibility option. The first office now starts without an artificial cooldown.")
    parser.add_argument("--codex-start-stagger", type=float, help="Deprecated compatibility alias for --office-show-delay; values above 5 are capped with warning evidence.")
    parser.add_argument("--codex-start-strategy", choices=("sequential", "batch"), default="sequential", help="Codex startup strategy. sequential is the safe default; batch starts up to --codex-batch-size panes together when estimated requests stay within the per-minute gate.")
    parser.add_argument("--codex-batch-size", type=int, default=SUPERCC_CODEX_BATCH_SIZE_DEFAULT, help="Maximum child Codex starts in one batch when --codex-start-strategy=batch.")
    parser.add_argument("--codex-batch-gap", type=float, help="Deprecated compatibility option. Provider queue timing is independent of office presentation.")
    parser.add_argument("--codex-start-jitter", type=float, default=SUPERCC_CODEX_START_JITTER_DEFAULT_SECONDS, help="Optional presentation jitter; office show delay plus jitter is always capped at 5 seconds.")
    parser.add_argument("--codex-retry-attempts", type=int, default=SUPERCC_CODEX_RETRY_ATTEMPTS_DEFAULT, help="Codex startup attempts inside each child pane. Default is 1 to avoid retry storms.")
    parser.add_argument("--codex-retry-backoff-base", type=float, default=SUPERCC_CODEX_RETRY_BACKOFF_DEFAULT_SECONDS, help="Provider retry backoff base. Default: 5 seconds; a provider Retry-After may be longer and is reported as queued_rate_limit.")
    parser.add_argument("--request-rate-limit-per-minute", type=int, default=SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE, help="Maximum model-triggering launches/dispatches per minute. Default: 20.")
    parser.add_argument("--request-total-limit", type=int, help="Optional total model-triggering request budget for the selected command, e.g. 20 for stress tests.")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def selected_action_name(args: argparse.Namespace) -> str:
    if args.super_entry:
        return "super_entry"
    if args.check_only:
        return "check_only"
    if args.write_agent_dossiers:
        return "write_agent_dossiers"
    if args.launch_three:
        return "launch_three"
    if args.launch_visible_core:
        return "launch_visible_core"
    if args.launch_offices:
        return "launch_offices"
    if args.turn_start:
        return "turn_start"
    if args.restart_offices:
        return "restart_offices"
    if args.closeout_silence:
        return "closeout_silence"
    if args.wake_offices:
        return "wake_offices"
    if args.patrol:
        return "patrol"
    if args.enter_dispatch:
        return "enter_dispatch"
    if args.dispatch_router_dry_run:
        return "dispatch_router_dry_run"
    if args.rename_taizi:
        return "rename_taizi"
    return "unknown"


def side_effect_manifest(args: argparse.Namespace, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    action = selected_action_name(args)
    dry_run = bool(args.dry_run or action == "dispatch_router_dry_run")
    read_operations: list[str] = []
    planned_if_live: list[str] = []
    applied: list[str] = []

    if action == "super_entry":
        read_operations = ["resolve_super_entry_client_plan", "inspect_zellij_environment", "inspect_squad_agents", "check_per_office_clients"]
        if getattr(args, "super_entry", None) in {"launch", "turn-start", "restart"}:
            planned_if_live = ["delegate_to_structured_supercc_action", "write_office_state_when_delegate_mutates"]
    elif action == "check_only":
        read_operations = ["inspect_zellij_environment", "inspect_squad_agents", "check_office_client"]
    elif action == "write_agent_dossiers":
        read_operations = ["read_standing_official_profiles"]
        planned_if_live = ["write_per_office_AGENTS_md_dossiers"]
    elif action in {"launch_three", "launch_visible_core", "launch_offices"}:
        read_operations = ["inspect_runtime_before_launch"]
        planned_if_live = ["write_per_office_AGENTS_md_dossiers", "launch_visible_office_panes", "join_squad_identities", "write_office_state"]
    elif action == "turn_start":
        read_operations = ["inspect_runtime_before_turn_start", "inspect_existing_squad_identities"]
        planned_if_live = [
            "release_noncurrent_inactive_squad_ids",
            "launch_or_reuse_visible_core",
            "send_turn_start_open_decree",
            "native_wake_visible_departments",
            "write_office_state",
        ]
    elif action == "restart_offices":
        read_operations = ["inspect_runtime_before_restart"]
        planned_if_live = ["archive_current_office_identities", "close_visible_office_panes", "launch_visible_office_panes", "send_turn_start_open_decree", "write_office_state"]
    elif action == "closeout_silence":
        read_operations = ["inspect_office_state_before_closeout"]
        planned_if_live = ["write_idle_receive_modes", "record_expected_closeout_silence"]
    elif action == "wake_offices":
        read_operations = ["inspect_office_state_before_wake"]
        planned_if_live = ["write_awake_modes", "send_wake_notices"]
    elif action == "patrol":
        read_operations = ["run_supercc_watchdog_status_script"]
    elif action == "enter_dispatch":
        read_operations = ["inspect_target_visible_pane", "inspect_office_state_before_dispatch"]
        planned_if_live = ["create_squad_task_assignment", "mirror_dispatch_to_squad", "native_enter_receive_command", "delayed_physical_enter", "write_dispatch_evidence"]
    elif action == "dispatch_router_dry_run":
        read_operations = ["inspect_runtime_client", "probe_dispatch_route", "plan_squad_first_receive_command_enter"]
    elif action == "rename_taizi":
        read_operations = ["inspect_current_pane"]
        planned_if_live = ["rename_current_pane", "join_taizi_identity"]

    # Intent is not execution evidence.  A failed live action must never report
    # every planned mutation as applied.  Mutating paths may opt in by returning
    # an explicit private evidence list after the operation succeeds.
    explicit_applied = (payload or {}).get("_applied_side_effects")
    applied_evidence = "not_inferred_from_plan"
    if not dry_run and isinstance(explicit_applied, list):
        applied = [str(item) for item in explicit_applied if str(item).strip()]
        applied_evidence = "explicit_runtime_evidence"
    elif not dry_run and planned_if_live and payload is not None:
        action_succeeded = bool(payload.get("ok", payload.get("passed", False)))
        if action_succeeded:
            applied = list(planned_if_live)
            applied_evidence = "top_level_action_success"

    return {
        "schema": "court.supercc.side_effects.v1",
        "selected_action": action,
        "dry_run": dry_run,
        "mutates_runtime": bool(applied),
        "read_operations": read_operations,
        "planned_if_live": planned_if_live,
        "applied": applied,
        "applied_evidence": applied_evidence,
        "policy": "check-only, super-entry plan/check, watchdog status, and dry-run commands must report no runtime mutation. Visible monitor mutation is disabled. superCC open-agent count is uncapped; model-triggering requests must stay <=20/min and within explicit total budgets.",
        "skip_inspector": bool(getattr(args, "skip_inspector", False)),
        "request_rate_limit_per_minute": requested_rate_limit_per_minute(args),
        "request_total_limit": getattr(args, "request_total_limit", None),
        "light_bootstrap_policy": SUPERCC_LIGHT_BOOTSTRAP_POLICY,
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"supercc_env_gate: {payload.get('supercc_env_gate', payload.get('check', {}).get('supercc_env_gate', 'UNKNOWN'))}",
        f"visible_display_gate: {payload.get('visible_display_gate', payload.get('check', {}).get('visible_display_gate', 'UNKNOWN'))}",
        f"office_client_gate: {payload.get('office_client_gate', payload.get('check', {}).get('office_client_gate', 'UNKNOWN'))}",
        f"ok: {payload.get('ok', payload.get('passed', False))}",
    ]
    side_effects = payload.get("side_effects")
    if isinstance(side_effects, dict):
        lines.append(
            "side_effects: "
            f"action={side_effects.get('selected_action')} "
            f"mutates_runtime={side_effects.get('mutates_runtime')} "
            f"applied={len(side_effects.get('applied') or [])}"
        )
    check = payload.get("check") or payload
    zellij = check.get("zellij", {})
    squad = check.get("squad", {})
    codex = check.get("codex", {})
    office_client = check.get("office_client", payload.get("office_client", {}))
    lines.append(f"zellij_inside: {zellij.get('inside')} session={zellij.get('env', {}).get('ZELLIJ_SESSION_NAME')} pane={zellij.get('env', {}).get('ZELLIJ_PANE_ID')}")
    lines.append(f"squad_doctor: {squad.get('doctor', {}).get('ok')}")
    lines.append(
        "office_client: "
        f"requested={office_client.get('requested_office_client')} "
        f"resolved={office_client.get('office_client')} "
        f"available={office_client.get('available')} "
        f"command={office_client.get('command')} "
        f"selection={office_client.get('selection_source')}"
    )
    lines.append(f"codex_available: {codex.get('available')}")
    if "dependency_bootstrap" in payload:
        bootstrap = payload["dependency_bootstrap"]
        lines.append(f"dependency_bootstrap: ok={bootstrap.get('ok')} skipped={bootstrap.get('skipped')} reason={bootstrap.get('reason', '')}")
    if payload.get("supercc_watchdog") or payload.get("silent_supervisor"):
        lines.append("")
        lines.append(
            "silent_supervisor: "
            f"{payload.get('silent_supervisor')} "
            f"watchdog={payload.get('supercc_watchdog')} "
            f"no_visible_window={payload.get('watchdog_no_visible_window')}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    selected_actions = (
        args.super_entry,
        args.check_only,
        args.write_agent_dossiers,
        args.launch_three,
        args.launch_visible_core,
        args.launch_offices,
        args.turn_start,
        args.restart_offices,
        args.closeout_silence,
        args.wake_offices,
        args.patrol,
        args.enter_dispatch,
        args.dispatch_router_dry_run,
        args.rename_taizi,
    )
    if sum(bool(flag) for flag in selected_actions) != 1:
        parser.error(
            "choose exactly one of --super-entry, --check-only, --write-agent-dossiers, --launch-three, --launch-visible-core, --launch-offices, "
            "--turn-start, --restart-offices, --closeout-silence, --wake-offices, "
            "--patrol, --enter-dispatch, --dispatch-router-dry-run, or --rename-taizi"
        )

    workspace = Path(args.workspace).resolve()
    transport_roles: tuple[str, ...] | None = None
    transport_preflight: dict[str, Any] | None = None
    try:
        if args.launch_offices:
            transport_roles = expand_transport_office_selection(args.launch_offices)
            candidate = special_lifecycle_transport_preflight(
                args,
                transport_roles,
                transport_action="launch_offices",
            )
            if not candidate["ok"]:
                transport_preflight = candidate
        elif args.wake_offices:
            transport_roles = expand_transport_office_selection(args.wake_offices)
            candidate = special_lifecycle_transport_preflight(
                args,
                transport_roles,
                transport_action="wake_offices",
                sender=args.calling_office or "shangshu",
            )
            if not candidate["ok"]:
                transport_preflight = candidate
    except ValueError as exc:
        parser.error(str(exc))

    if transport_preflight is None:
        resolve_office_client_args(args)
        try:
            normalize_office_client_maps(args)
        except ValueError as exc:
            parser.error(str(exc))

    if transport_preflight is not None:
        dependency_bootstrap = {
            "ok": True,
            "skipped": True,
            "reason": "special_lifecycle_authority_rejected_before_dependency_bootstrap",
        }
    elif args.write_agent_dossiers:
        dependency_bootstrap = {"ok": True, "skipped": True, "reason": "--write-agent-dossiers"}
    else:
        dependency_bootstrap = maybe_bootstrap_supercc_dependencies(args, workspace)
    if args.super_entry:
        try:
            payload = super_entry(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.check_only:
        payload = check_only(args)
    elif args.write_agent_dossiers:
        payload = write_agent_dossiers(args)
    elif args.launch_three:
        payload = launch_three(args)
    elif args.launch_visible_core:
        payload = launch_visible_core(args)
    elif args.launch_offices:
        if transport_preflight is not None:
            payload = transport_preflight
        else:
            payload = launch_offices(args, transport_roles or ())
    elif args.turn_start:
        try:
            payload = turn_start(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.restart_offices:
        try:
            payload = restart_offices(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.closeout_silence:
        try:
            payload = closeout_silence(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.wake_offices:
        if transport_preflight is not None:
            payload = transport_preflight
        else:
            payload = wake_roles(
                args,
                transport_roles or (),
                reason=args.wake_reason,
                sender=args.calling_office or "shangshu",
            )
    elif args.patrol:
        try:
            payload = watchdog_compat(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.enter_dispatch:
        try:
            payload = enter_dispatch(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.dispatch_router_dry_run:
        try:
            payload = dispatch_router_dry_run(args)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        payload = rename_taizi_only(args)
    delay_resolution = office_show_delay_resolution(args)
    payload.setdefault("office_show_delay", delay_resolution)
    payload.setdefault("office_show_delay_seconds", delay_resolution["effective_interval_seconds"])
    payload.setdefault("ordinary_spawn_delay_seconds", ordinary_spawn_delay_seconds())
    payload.setdefault("provider_rate_limit_state", QUEUED_RATE_LIMIT_STATE)
    payload["side_effects"] = side_effect_manifest(args, payload)
    payload["dependency_bootstrap"] = dependency_bootstrap
    if not dependency_bootstrap.get("ok", False):
        payload["supercc_env_gate"] = "runtime_degraded"
        payload["visible_display_gate"] = "runtime_degraded"
        payload["display_transport_gate"] = "runtime_degraded"
        payload["ok"] = False

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload))

    ok = bool(payload.get("ok", payload.get("passed", False)))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
