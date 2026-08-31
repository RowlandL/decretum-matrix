"""Manifest-derived read-only MCP projections.

The CLI command manifest is the single public command identity source. MCP
only projects entries explicitly marked with an ``mcp`` object; it does not
maintain a second allowlist or command schema.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "references" / "manifests" / "cli-command-surface.v1.json"


@dataclass(frozen=True)
class PublicTool:
    name: str
    description: str
    command_id: str
    public_api: str
    input_schema: dict[str, object]
    side_effect: str
    dry_run: bool


def _schema(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("mcp input_schema must be an object")
    schema = dict(value)
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError("mcp input_schema must be a closed object schema")
    return schema


def _load_manifest() -> dict[str, object]:
    try:
        value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"CLI command manifest unavailable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != "decretum.cli_command_surface.v1":
        raise ValueError("CLI command manifest schema invalid")
    return value


def load_public_tools() -> dict[str, PublicTool]:
    manifest = _load_manifest()
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("CLI command manifest entries must contain an array")
    records: dict[str, PublicTool] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        projection = entry.get("mcp")
        if projection is None:
            continue
        projections = projection if isinstance(projection, list) else [projection]
        for raw in projections:
            if not isinstance(raw, dict):
                raise ValueError(f"MCP projection for {entry.get('id')} must be an object")
            name = str(raw.get("name") or "").strip()
            description = str(raw.get("description") or "").strip()
            public_api = str(raw.get("public_api") or "").strip()
            command_id = str(entry.get("id") or "").strip()
            side_effect = str(raw.get("side_effect") or "").strip()
            dry_run = raw.get("dry_run") is True
            if not name or not description or not public_api or not command_id:
                raise ValueError(f"MCP projection for {command_id or '<unknown>'} is incomplete")
            if side_effect != "read_only":
                raise ValueError(f"MCP projection must be read_only: {name}")
            if name in records:
                raise ValueError(f"duplicate MCP tool: {name}")
            records[name] = PublicTool(
                name=name,
                description=description,
                command_id=command_id,
                public_api=public_api,
                input_schema=_schema(raw.get("input_schema")),
                side_effect=side_effect,
                dry_run=dry_run,
            )
    if not records:
        raise ValueError("CLI command manifest declares no MCP projections")
    return dict(sorted(records.items()))


def _type_matches(value: object, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }.get(expected, False)


def _validate_value(value: object, schema: Mapping[str, object], path: str) -> None:
    expected = schema.get("type")
    if isinstance(expected, str) and not _type_matches(value, expected):
        raise ValueError(f"{path}_must_be_{expected}")
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        if value not in enum:
            raise ValueError(f"{path}_must_be_one_of:{','.join(str(item) for item in enum)}")
    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        maximum_length = schema.get("maxLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            raise ValueError(f"{path}_below_min_length")
        if isinstance(maximum_length, int) and len(value) > maximum_length:
            raise ValueError(f"{path}_above_max_length")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and pattern and re.search(pattern, value) is None:
            raise ValueError(f"{path}_pattern_mismatch")
    if isinstance(value, dict):
        properties = schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ValueError(f"unknown_arguments:{','.join(str(item) for item in unknown)}")
        required = schema.get("required")
        if isinstance(required, list):
            missing = [str(item) for item in required if item not in value]
            if missing:
                raise ValueError(f"missing_arguments:{','.join(missing)}")
        for key, item in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                _validate_value(item, child_schema, f"{path}_{key}")
    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        maximum_items = schema.get("maxItems")
        if isinstance(minimum_items, int) and len(value) < minimum_items:
            raise ValueError(f"{path}_below_min_items")
        if isinstance(maximum_items, int) and len(value) > maximum_items:
            raise ValueError(f"{path}_above_max_items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_value(item, item_schema, f"{path}_{index}")
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(minimum, (int, float)) and value < minimum:
            raise ValueError(f"{path}_below_minimum")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise ValueError(f"{path}_above_maximum")


def invoke_public_tool(tool: PublicTool, arguments: object = None) -> dict[str, object]:
    args = {} if arguments is None else arguments
    if not isinstance(args, dict):
        raise ValueError("arguments_must_be_object")
    _validate_value(args, tool.input_schema, "argument")
    module = importlib.import_module("court_public_api")
    function = getattr(module, tool.public_api, None)
    if not callable(function):
        raise ValueError(f"public_api_unavailable:{tool.public_api}")
    result = function(**args)
    if not isinstance(result, dict):
        raise ValueError(f"public_api_result_invalid:{tool.public_api}")
    return result


def validate_public_tool_arguments(tool: PublicTool, arguments: object = None) -> None:
    """Validate wire arguments before the adapter emits a JSON-RPC result."""

    args = {} if arguments is None else arguments
    if not isinstance(args, dict):
        raise ValueError("arguments_must_be_object")
    _validate_value(args, tool.input_schema, "argument")
