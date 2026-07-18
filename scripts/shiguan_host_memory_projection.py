"""Pure host-memory and metadata-projection policy gates."""
import re


def _text(value): return str(value or "").strip()
def _result(ok, status, **data): return {"ok": bool(ok), "status": status, **data}
def _tool(value): return _text(value.get("tool_class") if isinstance(value, dict) else value)


def _installed(request):
    projection = request.get("install_projection", {}) if isinstance(request, dict) else {}
    return [item for item in projection.get("tools", []) if isinstance(item, dict)
            and item.get("court_skill_installed") is True
            and (_tool(item) in ("codex", "hermes", "claude-code")
                 or re.fullmatch(r"other:[a-z0-9][a-z0-9._-]*", _tool(item)))]


def evaluate_host_memory_projection(request):
    if not isinstance(request, dict): return _result(False, "REJECTED")
    get = request.get
    path = _text(get("target_path")).replace("\\", "/").casefold()
    marker = "/.codex/memories/extensions/ad_hoc/notes/"
    phase = _text(get("evaluation_phase"))
    status = {"planning": "NOTE_CANDIDATE_ALLOWED", "create_receipt": "NOTE_CREATED_PENDING_INGESTION",
              "ingestion_verification": "APPLIED_VERIFIED"}.get(phase, "")
    tail = path.split(marker, 1)[-1]
    base = all(get(key) is True for key in "newest_explicit_user_authorization menxia_approved append_only".split())
    base &= all(get(key) is False for key in "direct_memory_md_write contains_private_body".split())
    base &= get("current_agent") == get("target_agent") == "codex" and get("requested_status") == status
    base &= marker in path and tail.endswith(".md") and "/" not in tail
    receipt = get("create_only_receipt") if isinstance(get("create_only_receipt"), dict) else {}
    received = all((receipt.get("success") is True, receipt.get("write_mode") == "create_only",
                    bool(_text(receipt.get("receipt_id"))),
                    _text(receipt.get("target_path")).replace("\\", "/").casefold() == path,
                    bool(re.fullmatch(r"[0-9a-fA-F]{64}", _text(receipt.get("sha256"))))))
    proof = get("ingestion_verification") if isinstance(get("ingestion_verification"), dict) else {}
    verified = (get("ingestion_verified") is True and proof.get("confirmed") is True
                and proof.get("method") == "read_only" and bool(_text(proof.get("evidence_pointer"))))
    phase_ok = ((phase == "planning" and get("dry_run") is True and not get("ingestion_verified"))
                or (phase == "create_receipt" and received and not get("ingestion_verified"))
                or (phase == "ingestion_verification" and received and verified))
    return _result(base and phase_ok, status if base and phase_ok else "REJECTED")


def evaluate_installed_tool_memory_projection(request):
    callbacks = request.get("callbacks", {}) if isinstance(request, dict) else {}
    read = callbacks.get("read_source_metadata") if isinstance(callbacks, dict) else None
    if not callable(read): return _result(False, "BLOCKED")
    graphs, ok = {}, True
    for item in _installed(request):
        owner, nodes, edges = _tool(item), {}, []
        for raw in read(item):
            get = raw.get
            source = _text(get("relative_source_id") or get("source_id"))
            path = _text(get("relative_source_path")).replace("\\", "/")
            digest = _text(get("sha256") or get("fingerprint"))
            parts = path.split("/")
            relative = bool(path and not path.startswith("/") and not re.match(r"^[A-Za-z]:", path)
                            and all(part not in ("", ".", "..") for part in parts))
            valid, relations = bool(source.startswith(owner + ":") and relative and digest), []
            for relation in get("relations", []):
                target = _text(relation.get("target_id"))
                same = target.startswith(owner + ":") and _text(relation.get("target_tool_class")) in ("", owner)
                valid &= same
                if same:
                    relations.append({"source_id": source, "target_id": target})
                    nodes.setdefault(target, {"id": target})
                    edges.append({"source": source, "target": target})
            ok &= valid
            record = {"state": get("state") or "unknown", "headings": get("headings", []),
                      "topics": get("topics", [])}
            record.update(id=source, relative_source_id=source, relative_source_path=path,
                          sha256=digest, relations=relations)
            nodes[source] = record
        graphs[owner] = {"namespace": "memories/tools/" + owner.replace(":", "/"),
                         "nodes": list(nodes.values()), "edges": edges}
    return _result(ok, "METADATA_ONLY" if ok else "BLOCKED", graphs=graphs)


def evaluate_blank_host_memory_preflight(request):
    callbacks = request.get("callbacks", {}) if isinstance(request, dict) else {}
    probe = callbacks.get("probe_memory_feature") if isinstance(callbacks, dict) else None
    if not callable(probe): return _result(False, "BLOCKED")
    allowed = {_text(value) for value in request.get("newest_explicit_authorized_tool_classes", [])}
    results, blocked = {}, []
    for item in _installed(request):
        owner, raw = _tool(item), probe(item)
        state = _text(raw.get("status") or raw.get("state"))
        results[owner] = {"status": state, "evidence": list(raw.get("evidence", [])),
                          "prompt_required": True, "mutation_allowed": False,
                          "automatic_enablement_allowed": False}
        if owner not in allowed or state == "unknown": blocked.append(owner)
    return _result(True, "PREFLIGHT_COMPLETE", probe_results=results, blocked_mutations=blocked,
                   preflight_before_writes=True, prompt_required=True)
