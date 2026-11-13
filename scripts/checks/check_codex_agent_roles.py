"""Validate installed Codex agent role files rendered from standing profiles."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import json
from pathlib import Path
import stat
import sys
import tempfile

sys.dont_write_bytecode = True

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]

from sync_codex_agents_from_profiles import (
    REQUIRED_PROFILE_FILES,
    backup_toml_tree,
    installed_agents_root,
    render_agent_toml,
    template_root,
    codex_home,
)
from court_multi_agent_protocol import render_protocol_config, validate_protocol_config


from codex_role_diagnostics import (
    read_toml, schema_errors, validate_codex_multi_agent_config, validate_installed_agents,
)


def validate_immutable_backup_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="court-agent-backup-check-") as temp_dir:
        root = Path(temp_dir)
        source = root / "source"
        destination = root / "backup"
        source.mkdir()
        original = source / "taizi.toml"
        original.write_text('name = "taizi"\n', encoding="utf-8")
        assert backup_toml_tree(source, destination) == 1
        backed_up = destination / original.name
        assert backed_up.read_bytes() == original.read_bytes()
        assert not backed_up.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        try:
            backup_toml_tree(source, destination)
        except FileExistsError:
            pass
        else:
            raise AssertionError("backup destination must be non-overwrite")
        backed_up.chmod(stat.S_IREAD | stat.S_IWRITE)


def validate_managed_overlay_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="court-agent-overlay-check-") as temp_dir:
        root = Path(temp_dir)
        base = root / "config.toml"
        managed = root / "managed_config.toml"
        base.write_text(
            "[agents]\nmax_depth=4\n\n[features.multi_agent_v2]\nenabled=true\n"
            "max_concurrent_threads_per_session=16\nhide_spawn_agent_metadata=true\n",
            encoding="utf-8",
        )
        managed.write_text(
            "[agents]\nmax_depth=4\nmax_threads=15\n\n[features]\nmulti_agent=true\n\n"
            "[features.multi_agent_v2]\nenabled=false\nmax_concurrent_threads_per_session=16\n"
            "hide_spawn_agent_metadata=true\n",
            encoding="utf-8",
        )
        result = validate_codex_multi_agent_config(base, managed)
        assert result["ok"] is True
        assert result["selected_protocol"] == "v1"
        assert result["base_selected_protocol"] == "v2"
        assert result["config_layer_source"] == "legacy_managed_overlay"


def validate_native_config_contract() -> dict[str, int]:
    native = "[agents]\nmax_depth=4\nmax_concurrent_threads_per_session=32\n"
    positives = (
        (native, 32),
        (native + "\n[features]\nmulti_agent=true\n", 32),
        (native + "\n[features]\nmulti_agent=true\nmulti_agent_v2=false\n", 32),
        (native.replace("=32", "=1"), 1),
    )
    legacy = {
        "v1": "[agents]\nmax_depth=4\nmax_threads=15\n[features]\nmulti_agent=true\n"
              "[features.multi_agent_v2]\nenabled=false\nmax_concurrent_threads_per_session=16\nhide_spawn_agent_metadata=true\n",
        "v2": "[agents]\nmax_depth=4\n[features.multi_agent_v2]\nenabled=true\n"
              "max_concurrent_threads_per_session=16\nhide_spawn_agent_metadata=true\n",
        "serial": "[agents]\nmax_depth=4\n[features]\nmulti_agent=false\n[features.multi_agent_v2]\nenabled=false\n",
    }
    negatives = ["", "[agents]\nmax_depth=4\n"]
    negatives.extend(
        native.replace("=32", "=" + value)
        for value in ("true", "false", "0", "-1", "1.5", '"32"')
    )
    negatives.extend(
        native.replace("max_depth=4", "max_depth=" + value)
        for value in ("true", "false", "3", "5", "4.0", '"4"')
    )
    negatives.extend(
        native + "\n[features]\nmulti_agent=" + value + "\n"
        for value in ("false", "1", '"true"')
    )
    negatives.extend(
        native + "\n[features]\nmulti_agent_v2=" + value + "\n"
        for value in ("true", "1", '"false"')
    )
    negatives.extend((
        "features=false\n" + native,
        "features=[]\n" + native,
        native + "max_threads=32\n",
    ))
    with tempfile.TemporaryDirectory(prefix="court-native-config-check-") as temp_dir:
        root = Path(temp_dir).resolve()
        base, overlay = root / "config.toml", root / "managed_config.toml"
        for text, children in positives:
            base.write_text(text, encoding="utf-8")
            before = base.read_bytes()
            result = validate_codex_multi_agent_config(base, overlay)
            assert result["ok"] is True and result["selected_protocol"] == "v1"
            assert result["max_threads"] == result["max_concurrent_threads_per_session"] == result["effective_child_thread_limit"] == children
            assert result["logical_total_threads"] == children + 1
            assert result["spawn_agent_metadata_claim_scope"] == "CONFIG_ONLY_NOT_RUNTIME_SCHEMA"
            assert result["runtime_spawn_schema_inferred_from_config"] is False
            assert base.read_bytes() == before
        for mode, text in legacy.items():
            base.write_text(text, encoding="utf-8")
            result = validate_codex_multi_agent_config(base, overlay)
            assert result["ok"] is True and result["selected_protocol"] == mode
            if mode != "serial":
                assert result["effective_child_thread_limit"] == 15 and result["logical_total_threads"] == 16
        for mode in ("v1", "v2"):
            base.write_text(render_protocol_config(native, mode, total_threads=33), encoding="utf-8")
            result = validate_codex_multi_agent_config(base, overlay)
            assert result["ok"] is True and result["selected_protocol"] == mode
            assert result["effective_child_thread_limit"] == 32 and result["logical_total_threads"] == 33
        for text in negatives:
            base.write_text(text, encoding="utf-8")
            before = base.read_bytes()
            assert validate_codex_multi_agent_config(base, overlay)["ok"] is False, text
            assert base.read_bytes() == before
        assert validate_protocol_config(native, expected_mode="v2")["ok"] is False
        base.write_text(legacy["v2"], encoding="utf-8")
        overlay.write_text(native, encoding="utf-8")
        result = validate_codex_multi_agent_config(base, overlay)
        assert result["ok"] is True and result["selected_protocol"] == "v1"
        assert result["base_selected_protocol"] == "v2" and result["effective_child_thread_limit"] == 32
        assert result["config_layer_source"] == "legacy_managed_overlay"
        overlay.write_text(native.replace("=32", "=true"), encoding="utf-8")
        assert validate_codex_multi_agent_config(base, overlay)["ok"] is False
    return {"native_positive": len(positives), "legacy_positive": len(legacy), "producer_positive": 2,
            "negative": len(negatives) + 1, "layer": 2}


def validate_ordinary_carrier_projection_contract() -> None:
    templates = template_root()
    for name in ("zhongshu.toml", "patrol-inspector.toml"):
        role = Path(name).stem
        rendered = render_agent_toml(templates / name)
        assert tomllib is not None
        parsed = tomllib.loads(rendered)
        normalized = (
            str(parsed.get("description") or "")
            + "\n"
            + str(parsed.get("developer_instructions") or "")
        ).replace("\\", "/").casefold()
        expected_dossier = f"agents/office-dossiers/{role}/agents.md"
        assert expected_dossier in normalized, f"{role}: ordinary dossier pointer missing"
        assert "agents/supercc-dossiers/" not in normalized, f"{role}: visible carrier dossier leaked"
        for forbidden in ("supercc", "squad", "zellij"):
            assert forbidden not in normalized, f"{role}: ordinary projection leaked {forbidden}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()
    try:
        validate_immutable_backup_contract()
        validate_managed_overlay_contract()
        validate_native_config_contract()
        validate_ordinary_carrier_projection_contract()
        result = validate_installed_agents()
    except Exception as exc:
        print(f"CODEX_AGENT_ROLES_FAILED {exc}")
        return 1
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(
            "CODEX_AGENT_ROLES_OK "
            f"installed_count={result['installed_count']} required_count={result['required_count']} "
            f"malformed_count={result['malformed_count']} unsynced_count={result['unsynced_count']} "
            f"reserved_spawn_schema_compatible={result['config_contract']['reserved_spawn_schema_compatible']} "
            f"runtime_spawn_schema_visibility={result['config_contract']['runtime_spawn_schema_visibility']}"
        )
    else:
        print(
            "CODEX_AGENT_ROLES_FAILED "
            f"installed_count={result['installed_count']} required_count={result['required_count']} "
            f"malformed_count={result['malformed_count']} unsynced_count={result['unsynced_count']} "
            f"config_errors={','.join(result['config_contract']['errors'])}"
        )
        for row in result["schema_rows"]:
            if row["schema_status"] != "ok":
                print(f"malformed {row['agent']}: {', '.join(row['errors'])}")
        for row in result["sync_rows"]:
            if row["status"] != "synced":
                print(f"unsynced {row['agent']}: {row['status']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
