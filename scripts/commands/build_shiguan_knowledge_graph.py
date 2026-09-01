"""Build a lightweight multidimensional Shiguan knowledge graph."""

from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from shiguan_entry_utils import enrich_entry
from shiguan_paths import code_root, ensure_shared_seed, reference_path


def skill_root() -> Path:
    return code_root()


def index_path() -> Path:
    ensure_shared_seed()
    return reference_path("shiguan-index.jsonl")


def graph_path() -> Path:
    ensure_shared_seed()
    return reference_path("shiguan-knowledge-graph.json")


def load_entries() -> list[dict[str, object]]:
    path = index_path()
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            enrich_entry(value)
            entries.append(value)
    return entries


def node_id(kind: str, value: object) -> str:
    text = str(value or "unknown").strip() or "unknown"
    return f"{kind}:{text}"


def add_node(nodes: dict[str, dict[str, object]], kind: str, label: object, **attrs: object) -> str:
    ident = node_id(kind, label)
    if ident not in nodes:
        nodes[ident] = {"id": ident, "kind": kind, "label": str(label or "unknown"), "count": 0}
    nodes[ident]["count"] = int(nodes[ident].get("count", 0)) + 1
    nodes[ident].update({key: value for key, value in attrs.items() if value not in (None, "", [])})
    return ident


def add_edge(edges: Counter[tuple[str, str, str]], source: str, target: str, relation: str) -> None:
    if source and target:
        edges[(source, target, relation)] += 1


def build_graph(entries: list[dict[str, object]]) -> dict[str, object]:
    nodes: dict[str, dict[str, object]] = {}
    edges: Counter[tuple[str, str, str]] = Counter()
    root = add_node(nodes, "root", "史馆总纪")

    for entry in entries:
        entry_id = str(entry.get("record_uid") or entry.get("id") or entry.get("court_code") or entry.get("topic") or "")
        record = add_node(
            nodes,
            "record",
            entry_id,
            topic=entry.get("topic", ""),
            court_code=entry.get("court_code", ""),
            kb_uid=entry.get("kb_uid", ""),
            record_uid=entry.get("record_uid", ""),
            summary=entry.get("display_summary_zh") or entry.get("keyword_summary_zh") or entry.get("summary", ""),
            reason=entry.get("display_reason_zh") or entry.get("memory_reason") or entry.get("next", ""),
        )
        add_edge(edges, root, record, "records")

        lineage_parts = entry.get("lineage_parts")
        previous = root
        if isinstance(lineage_parts, dict):
            for level in ("zhi", "men", "gang", "mu", "tiao", "zhao"):
                value = lineage_parts.get(level)
                if not value:
                    continue
                node = add_node(nodes, f"lineage:{level}", value, dimension="内容谱系")
                add_edge(edges, previous, node, "narrows_to")
                add_edge(edges, record, node, "about")
                previous = node

        for keyword in entry.get("keywords_zh", [])[:12]:
            keyword_node = add_node(nodes, "keyword", keyword, dimension="关键词")
            add_edge(edges, record, keyword_node, "mentions")

        capability_lineage = entry.get("capability_lineage")
        if isinstance(capability_lineage, dict):
            for dimension, values in capability_lineage.items():
                dimension_node = add_node(nodes, "capability_dimension", dimension, dimension="能力谱系向量")
                add_edge(edges, root, dimension_node, "has_capability_dimension")
                if not isinstance(values, list):
                    values = [values]
                for value in values:
                    capability_node = add_node(nodes, "capability_vector", value, dimension=dimension)
                    add_edge(edges, dimension_node, capability_node, "has_value")
                    add_edge(edges, record, capability_node, "capability_related")
        for source_path in entry.get("capability_source_paths", [])[:8]:
            path_node = add_node(nodes, "source_path", source_path, dimension="源路径")
            add_edge(edges, record, path_node, "source_path")

        facets = entry.get("facet_dimensions")
        if isinstance(facets, dict):
            for dimension, values in facets.items():
                dimension_node = add_node(nodes, "dimension", dimension)
                add_edge(edges, root, dimension_node, "has_dimension")
                if not isinstance(values, list):
                    values = [values]
                for value in values:
                    facet_node = add_node(nodes, "facet", value, dimension=dimension)
                    add_edge(edges, dimension_node, facet_node, "has_value")
                    add_edge(edges, record, facet_node, "faceted_by")

    return {
        "schema": {
            "name": "shiguan-multidimensional-knowledge-graph",
            "version": 1,
            "rule": "主干按内容谱系；朝程压缩为大阶段，状态、记忆和诏令行为拆为独立分面；关键词、评估、来源、时间作为旁通召回。",
            "edge_model": "lightweight subject-predicate-object graph encoded as JSON nodes and edges.",
        },
        "counts": {"entries": len(entries), "nodes": len(nodes), "edges": len(edges)},
        "nodes": sorted(nodes.values(), key=lambda item: (str(item.get("kind", "")), str(item.get("label", "")))),
        "edges": [
            {"source": source, "target": target, "relation": relation, "weight": weight}
            for (source, target, relation), weight in sorted(edges.items())
        ],
    }


def build_and_write() -> tuple[int, Path]:
    entries = load_entries()
    graph = build_graph(entries)
    path = graph_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return len(entries), path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    count, path = build_and_write()
    if not args.quiet:
        print(f"SHIGUAN_KG_OK {path} entries={count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())



