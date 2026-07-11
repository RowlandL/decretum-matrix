"""Export the built-in Shiguan tree as an Obsidian-compatible vault."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import re
import shutil
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import tempfile
import zipfile
from court_platform import user_data_base
from shiguan_paths import code_root, ensure_shared_seed, reference_path, references_root as shared_references_root, shared_root


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MANAGED_EXPORT_MARKER = ".court-shiguan-managed.json"
MANAGED_EXPORT_SCHEMA = "court.shiguan.managed-export.v1"
PRESERVE_CACHE_MANIFEST = ".court-shiguan-sync-manifest.json"


def skill_root() -> Path:
    return code_root()


def tree_root() -> Path:
    ensure_shared_seed()
    return reference_path("shiguan-tree")


def references_root() -> Path:
    ensure_shared_seed()
    return shared_references_root()


def safe_out(path_text: str) -> Path:
    path = Path(path_text).expanduser().resolve()
    skill = skill_root().resolve()
    data = shared_root().resolve()
    if path == skill or skill in path.parents or path in skill.parents:
        raise ValueError("Refusing to export inside the source skill directory.")
    if path == data or data in path.parents or path in data.parents:
        raise ValueError("Refusing to export inside the shared Shiguan database.")
    return path


def managed_marker_path(path: Path) -> Path:
    return path / MANAGED_EXPORT_MARKER


def valid_managed_marker(path: Path) -> bool:
    marker = managed_marker_path(path)
    if not marker.is_file():
        return False
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get("schema") == MANAGED_EXPORT_SCHEMA


def export_destination_mode(path: Path) -> str:
    path = safe_out(str(path))
    if not path.exists():
        return "fresh"
    if not path.is_dir():
        raise ValueError("Refusing to replace a non-directory export target.")
    if (path / PRESERVE_CACHE_MANIFEST).is_file():
        raise ValueError(
            "Refusing wholesale export replacement of a preserve-only Obsidian cache. "
            "Use sync_shiguan_obsidian_vault.py instead."
        )
    if valid_managed_marker(path):
        return "managed"
    if not any(path.iterdir()):
        return "empty"
    raise ValueError(
        f"Refusing to replace unknown non-empty directory without {MANAGED_EXPORT_MARKER}."
    )


def write_managed_marker(path: Path) -> None:
    managed_marker_path(path).write_text(
        json.dumps(
            {
                "schema": MANAGED_EXPORT_SCHEMA,
                "managed_by": "court-capability-router",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def ensure_tree() -> Path:
    from grow_shiguan_tree import grow_tree

    grow_tree()
    return tree_root()


def populate_export_tree(out: Path, src: Path) -> None:
    shutil.copytree(src, out)
    copy_sources(out)
    rewrite_source_links(out)
    redact_export_texts(out)
    ensure_export_frontmatter(out)
    write_managed_marker(out)
    (out / "Import Readme.md").write_text(
        "\n".join(
            [
                "---",
                "type: shiguan_obsidian_import_readme",
                f"exported_at: \"{datetime.now().isoformat(timespec='seconds')}\"",
                "---",
                "",
                "# Court Shiguan Obsidian Import",
                "",
                "Open this folder directly as an Obsidian vault, or copy its Markdown files into an existing vault.",
                "",
                "This export intentionally omits `.obsidian` settings and community plugin configuration.",
                "",
                "Start at [[_index]].",
                "",
                "Machine-readable recall files are under `sources/`, including `shiguan-index.jsonl` and `shiguan-knowledge-graph.json` when available.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )


def copy_tree(out: Path) -> None:
    out = safe_out(str(out))
    mode = export_destination_mode(out)
    src = ensure_tree()
    out.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    removed_empty = False
    with tempfile.TemporaryDirectory(prefix=f".{out.name}.stage-", dir=str(out.parent)) as temp_text:
        stage = Path(temp_text) / out.name
        populate_export_tree(stage, src)
        try:
            if out.exists():
                if mode == "empty":
                    out.rmdir()
                    removed_empty = True
                else:
                    backup = out.with_name(f".{out.name}.backup-{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
                    out.replace(backup)
            stage.replace(out)
        except Exception:
            if backup is not None and backup.exists() and not out.exists():
                backup.replace(out)
            elif removed_empty and not out.exists():
                out.mkdir()
            raise
    if backup is not None and backup.exists():
        shutil.rmtree(backup)


def redact_text(text: str) -> str:
    home = str(Path.home())
    user_name = Path.home().name
    local_app_data = str(user_data_base())
    replacements = {
        local_app_data: "%LOCALAPPDATA%",
        local_app_data.replace("\\", "\\\\"): "%LOCALAPPDATA%",
        home: "%USERPROFILE%",
        home.replace("\\", "\\\\"): "%USERPROFILE%",
        f"Users\\{user_name}": "%USERPROFILE%",
        f"Users\\\\{user_name}": "%USERPROFILE%",
    }
    redacted = text
    for needle, replacement in replacements.items():
        redacted = redacted.replace(needle, replacement)
    redacted = re.sub(r"[A-Za-z]:\\\\Users\\\\[^\\\\\s\"']+", "%USERPROFILE%", redacted)
    redacted = re.sub(r"[A-Za-z]:\\Users\\[^\\\s\"']+", "%USERPROFILE%", redacted)
    redacted = redacted.replace("AppData\\Local", "%LOCALAPPDATA%")
    redacted = redacted.replace("AppData\\\\Local", "%LOCALAPPDATA%")
    return redacted


def redact_export_texts(out: Path) -> None:
    for path in out.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".jsonl", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(redact_text(text), encoding="utf-8", newline="\n")


def copy_sources(out: Path) -> None:
    sources_root = out / "sources"
    for name in ("plan-archives", "memory-decisions"):
        source_dir = references_root() / name
        if source_dir.exists():
            target_dir = sources_root / name
            target_dir.mkdir(parents=True, exist_ok=True)
            for source_file in source_dir.rglob("*"):
                if not source_file.is_file():
                    continue
                target_file = target_dir / source_file.relative_to(source_dir)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                if source_file.suffix.lower() in {".md", ".json", ".jsonl", ".txt"}:
                    text = source_file.read_text(encoding="utf-8", errors="replace")
                    target_file.write_text(redact_text(text), encoding="utf-8", newline="\n")
                else:
                    shutil.copy2(source_file, target_file)
    manual_dir = tree_root() / "manual"
    if manual_dir.exists():
        target_dir = sources_root / "shiguan-tree" / "manual"
        target_dir.mkdir(parents=True, exist_ok=True)
        for source_file in manual_dir.rglob("*.json"):
            target_file = target_dir / source_file.relative_to(manual_dir)
            target_file.parent.mkdir(parents=True, exist_ok=True)
            text = source_file.read_text(encoding="utf-8", errors="replace")
            target_file.write_text(redact_text(text), encoding="utf-8", newline="\n")
    index = references_root() / "shiguan-index.jsonl"
    if index.exists():
        sources_root.mkdir(parents=True, exist_ok=True)
        text = index.read_text(encoding="utf-8", errors="replace")
        (sources_root / "shiguan-index.jsonl").write_text(
            redact_text(text),
            encoding="utf-8",
            newline="\n",
        )
    graph = references_root() / "shiguan-knowledge-graph.json"
    if graph.exists():
        sources_root.mkdir(parents=True, exist_ok=True)
        text = graph.read_text(encoding="utf-8", errors="replace")
        (sources_root / "shiguan-knowledge-graph.json").write_text(
            redact_text(text),
            encoding="utf-8",
            newline="\n",
        )


def rewrite_source_links(out: Path) -> None:
    for path in markdown_files(out / "leaves"):
        text = path.read_text(encoding="utf-8")
        text = text.replace("](../../plan-archives/", "](../sources/plan-archives/")
        text = text.replace("](../../memory-decisions/", "](../sources/memory-decisions/")
        text = text.replace("](../manual/", "](../sources/shiguan-tree/manual/")
        text = text.replace("](../../shiguan-tree/manual/", "](../sources/shiguan-tree/manual/")
        path.write_text(text, encoding="utf-8", newline="\n")


def ensure_export_frontmatter(out: Path) -> None:
    for path in markdown_files(out):
        relative = path.relative_to(out)
        if relative.parts and relative.parts[0] == "sources":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if has_frontmatter(text):
            continue
        path.write_text(
            "\n".join(
                [
                    "---",
                    "type: shiguan_obsidian_note",
                    f"exported_at: \"{datetime.now().isoformat(timespec='seconds')}\"",
                    "---",
                    "",
                    text.rstrip(),
                    "",
                ]
            ),
            encoding="utf-8",
            newline="\n",
        )


def markdown_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def has_frontmatter(text: str) -> bool:
    return text.startswith("---\n") and "\n---\n" in text[4:]


def check_export(out: Path) -> list[str]:
    errors: list[str] = []
    files = markdown_files(out)
    stems = {path.stem for path in files}
    link_paths = {path.relative_to(out).with_suffix("").as_posix() for path in files}
    for path in files:
        is_source = path.relative_to(out).parts[0] == "sources"
        text = path.read_text(encoding="utf-8")
        if not is_source and not has_frontmatter(text):
            errors.append(f"FRONTMATTER_MISSING {path}")
        if not is_source:
            for target in WIKILINK_RE.findall(text):
                if target not in stems and target not in link_paths:
                    errors.append(f"WIKILINK_BROKEN {path} -> {target}")
        if "C:\\Users\\" in text or "AppData\\Local" in text:
            errors.append(f"ABSOLUTE_PATH_LEAK {path}")
        if not is_source:
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if link.startswith(("http://", "https://", "mailto:")):
                    continue
                target = (path.parent / link).resolve()
                if not target.exists():
                    errors.append(f"MARKDOWN_LINK_BROKEN {path} -> {link}")
    if not (out / "_index.md").exists():
        errors.append(f"INDEX_MISSING {out / '_index.md'}")
    if not files:
        errors.append(f"NO_MARKDOWN {out}")
    return errors


def zip_dir(out: Path) -> Path:
    zip_path = out.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(out.parent))
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output folder, e.g. .\\dist\\Court Shiguan")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--zip", action="store_true")
    args = parser.parse_args()

    try:
        out = safe_out(args.out)
        copy_tree(out)
    except (OSError, ValueError) as exc:
        print(f"EXPORT_FAILED {exc}", file=sys.stderr)
        return 1

    if args.check:
        errors = check_export(out)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 2

    if args.zip:
        zip_path = zip_dir(out)
        print(f"OBSIDIAN_ZIP_OK {zip_path}")
    print(f"OBSIDIAN_EXPORT_OK {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
