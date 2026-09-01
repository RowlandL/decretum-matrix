"""M2/M3 install-root and release-bypass review gate (execution-book 6.1).

Bounded test/script-layer RED/GREEN evidence for the eight RED scenarios of
execution-book L177 plus the Menxia R7 per-root typed receipt fixture
caliber.  All roots are tempfile fixtures inside an isolated directory; this
checker performs zero writes to real install roots.  It is entry-evidence
caliber only: real installed per-root receipts remain a mandatory M3 item and
nothing here constitutes authorization for real root writes.

Output: COURT_INSTALL_RELEASE_BOUNDARY=PASS (GREEN, default).  --red replays
the same scenario assertions against a documented permissive legacy-style stub
(fixed-five fanout, silent omission of unproven targets), reproducing the RED
baseline where every scenario must be detected as unprotected.

Scope statement (correctness review M2): the RED demonstration of the eight
scenarios uses the legacy install-path stub as its baseline, to prove the
exposure surface when no mandatory gate exists; it is NOT an audit of the
current install-projection code.
"""



from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True

CONTRACT = "COURT_INSTALL_RELEASE_BOUNDARY"
SCHEMA = "court.install_release_boundary_check.v1"
ROOT_SELECTION_SCHEMA = "court.install.root_selection_receipt.v1"
ROOT_PROOF_SCHEMA = "court.install.root_authority_proof.v1"
SCOPED_PACKAGE = "@rowlandl/decretum-matrix"
REGISTRY = "https://npm.pkg.github.com"
ACCEPTED_VERSION = "1.0.6"
ROOT_SELECTION_REQUIRED = (
    "schema", "selection_policy", "primary_root", "current_tool",
    "current_tool_root", "current_tool_root_proof", "status",
    "explicit_extra_targets", "selected_roots", "authority", "receipt_sha256",
)
ROOT_PROOF_REQUIRED = (
    "schema", "target_root", "path_identity", "host_tool_provenance",
    "opt_in", "preimage_sha256", "backup_rollback", "post_write_proof",
    "authority",
)


def canonical_sha256(payload: object) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def resign_receipt(receipt: dict) -> dict:
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    receipt["receipt_sha256"] = canonical_sha256(body)
    return receipt


def physical_identity(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()

def evaluate_root_write_plan_strict(receipt, per_root_proofs, plan):
    """Target-contract evaluator: receipt-driven, per-root proof, fail closed."""
    rejections = []
    if not isinstance(receipt, dict):
        return {"decision": "REJECTED",
                "rejections": ["receipt_missing_or_schema", "fail_closed_zero_write"]}
    if receipt.get("schema") != ROOT_SELECTION_SCHEMA:
        rejections.append("receipt_missing_or_schema")
    for key in ROOT_SELECTION_REQUIRED:
        if receipt.get(key) in (None, ""):
            rejections.append(f"receipt_field_missing:{key}")
    for key in ("selected_roots", "explicit_extra_targets"):
        if not isinstance(receipt.get(key), list):
            rejections.append(f"receipt_field_not_list:{key}")
    unknown = sorted(set(receipt) - set(ROOT_SELECTION_REQUIRED))
    if unknown:
        rejections.append(f"receipt_unknown_fields:{','.join(unknown)}")
    if receipt.get("status") != "VERIFIED":
        rejections.append("receipt_status_not_verified")
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    if receipt.get("receipt_sha256") != canonical_sha256(body):
        rejections.append("receipt_digest_mismatch")
    if receipt.get("current_tool_root") and not receipt.get("current_tool_root_proof"):
        rejections.append("current_tool_unproven")
    proof_index = {}
    for proof in per_root_proofs or []:
        if not isinstance(proof, dict):
            rejections.append("root_proof_invalid:not_mapping")
            continue
        problems = []
        if proof.get("schema") != ROOT_PROOF_SCHEMA:
            problems.append("schema_mismatch")
        for key in ROOT_PROOF_REQUIRED:
            if proof.get(key) in (None, ""):
                problems.append(f"field_missing:{key}")
        unknown_p = sorted(set(proof) - set(ROOT_PROOF_REQUIRED))
        if unknown_p:
            problems.append("unknown_fields:" + ",".join(unknown_p))
        if problems:
            rejections.append("root_proof_invalid:" + str(proof.get("target_root")) + ":" + ";".join(problems))
            continue
        proof_index[str(proof["target_root"])] = proof
    selected = [str(root) for root in (receipt.get("selected_roots") or [])]
    identities = plan.get("root_identities") or {}
    for root in selected:
        proof = proof_index.get(root)
        if proof is None:
            rejections.append(f"root_missing_per_root_proof:{root}")
            continue
        if "qoder" in root and proof.get("opt_in") is not True:
            rejections.append(f"qoder_not_opted_in:{root}")
        expected = identities.get(root)
        if expected is not None and proof.get("path_identity") != expected:
            rejections.append(f"root_alias_physical_mismatch:{root}")
    candidate = plan.get("candidate") or {}
    if candidate.get("package") != SCOPED_PACKAGE:
        rejections.append("package_scope_mismatch")
    if candidate.get("registry") != REGISTRY:
        rejections.append("registry_mismatch")
    if str(candidate.get("version") or "") != ACCEPTED_VERSION:
        rejections.append("stale_beta_version")
    manifest = candidate.get("manifest")
    if not isinstance(manifest, dict) or candidate.get("artifact_sha256") != canonical_sha256(manifest):
        rejections.append("package_mutated_after_candidate_hash")
    write_roots = [str(root) for root in (plan.get("write_roots") or [])]
    for root in write_roots:
        if root == "~/.agent":
            rejections.append("root_alias_forbidden")
        if root not in selected:
            rejections.append(f"fanout_root_not_selected:{root}")
    if sorted(write_roots) != sorted(selected):
        rejections.append("receipt_write_root_set_mismatch")
    return {"decision": "REJECTED" if rejections else "APPROVED", "rejections": rejections}

def evaluate_root_write_plan_legacy_stub(receipt, per_root_proofs, plan):
    """Documented RED baseline: legacy fixed-five fanout behavior (plan L96).
 
    Ignores receipts, silently omits unproven targets and approves fanout.
    Exists only so the scenario suite demonstrates RED against unprotected
    behavior; it is never used in GREEN mode.

    Scope statement (correctness review M2): the RED demonstration of the
    eight scenarios uses this legacy install-path stub as its baseline, to
    prove the exposure surface when no mandatory gate exists; it is NOT an
    audit of the current install-projection code.
    """
    return {"decision": "APPROVED", "rejections": [], "note": "legacy_fixed_five_fanout"}

def build_fixture(base: Path):
    roots = {}
    for name in ("agents", "codex-tool", "qoder"):
        root = base / name
        root.mkdir(parents=True, exist_ok=True)
        roots[name] = root

    def proof(name, opt_in=True, identity_ok=True):
        return {
            "schema": ROOT_PROOF_SCHEMA,
            "target_root": name,
            "path_identity": physical_identity(roots[name]) if identity_ok else "0" * 64,
            "host_tool_provenance": f"host-provenance-{name}",
            "opt_in": opt_in,
            "preimage_sha256": hashlib.sha256(b"").hexdigest(),
            "backup_rollback": {"enabled": True, "strategy": "preimage-restore"},
            "post_write_proof": f"post-write-proof-{name}",
            "authority": "user-2026-08-06-explicit",
        }
    manifest = {
        "package": SCOPED_PACKAGE,
        "version": ACCEPTED_VERSION,
        "head": "48ddc910abc1829f04ac23f0430b55a1d3f0fea8",
    }
    candidate = {
        "package": SCOPED_PACKAGE,
        "registry": REGISTRY,
        "version": ACCEPTED_VERSION,
        "manifest": manifest,
        "artifact_sha256": canonical_sha256(manifest),
    }
    receipt = {
        "schema": ROOT_SELECTION_SCHEMA,
        "selection_policy": "receipt-driven-exact",
        "primary_root": "agents",
        "current_tool": "codex",
        "current_tool_root": "codex-tool",
        "current_tool_root_proof": "current-tool-root-proof-codex",
        "status": "VERIFIED",
        "explicit_extra_targets": ["qoder"],
        "selected_roots": ["agents", "codex-tool"],
        "authority": "user-2026-08-06-explicit",
        "receipt_sha256": "",
    }
    resign_receipt(receipt)
    proofs = [proof("agents"), proof("codex-tool"), proof("qoder")]
    identities = {name: physical_identity(path) for name, path in roots.items()}
    plan = {
        "candidate": candidate,
        "write_roots": ["agents", "codex-tool"],
        "root_identities": identities,
    }
    return roots, receipt, proofs, plan

def _qoder_proof(proofs):
    return next(proof for proof in proofs if proof.get("target_root") == "qoder")


def _mutate_receipt_missing(receipt, proofs, plan):
    return None, proofs, plan


def _mutate_provenance_missing(receipt, proofs, plan):
    for proof in proofs:
        if proof.get("target_root") == "agents":
            proof["host_tool_provenance"] = None
    return receipt, proofs, plan

def _mutate_fanout(receipt, proofs, plan):
    plan["write_roots"] = list(plan["write_roots"]) + ["hermes-tool"]
    return receipt, proofs, plan


def _mutate_qoder_not_opted_in(receipt, proofs, plan):
    receipt["selected_roots"] = list(receipt["selected_roots"]) + ["qoder"]
    resign_receipt(receipt)
    _qoder_proof(proofs)["opt_in"] = False
    return receipt, proofs, plan

def _mutate_alias_mismatch(receipt, proofs, plan):
    receipt["selected_roots"] = list(receipt["selected_roots"]) + ["qoder"]
    resign_receipt(receipt)
    _qoder_proof(proofs)["path_identity"] = "0" * 64
    return receipt, proofs, plan


def _mutate_stale_beta(receipt, proofs, plan):
    plan["candidate"]["version"] = "1.0.5-beta.0"
    return receipt, proofs, plan

def _mutate_wrong_scope_registry(receipt, proofs, plan):
    plan["candidate"]["package"] = "decretum-matrix"
    plan["candidate"]["registry"] = "https://registry.npmjs.org"
    return receipt, proofs, plan


def _mutate_mutator_after_hash(receipt, proofs, plan):
    plan["candidate"]["manifest"]["poisoned"] = "rewritten-after-candidate-hash"
    return receipt, proofs, plan

def _mutate_write_root_mismatch(receipt, proofs, plan):
    plan["write_roots"] = ["agents"]
    return receipt, proofs, plan


def build_scenarios():
    return [
        {"id": "1", "name": "receipt_or_provenance_missing",
         "expect": ["receipt_missing_or_schema"],
         "mutate": _mutate_receipt_missing},
        {"id": "1b", "name": "per_root_provenance_missing",
         "expect": ["root_proof_invalid"],
         "mutate": _mutate_provenance_missing},
        {"id": "2", "name": "non_current_tool_fanout",
         "expect": ["fanout_root_not_selected"],
         "mutate": _mutate_fanout},
        {"id": "3", "name": "qoder_not_opted_in",
         "expect": ["qoder_not_opted_in"],
         "mutate": _mutate_qoder_not_opted_in},
        {"id": "4", "name": "root_alias_physical_mismatch",
         "expect": ["root_alias_physical_mismatch"],
         "mutate": _mutate_alias_mismatch},
        {"id": "5", "name": "stale_beta",
         "expect": ["stale_beta_version"],
         "mutate": _mutate_stale_beta},
        {"id": "6", "name": "wrong_registry_package_scope",
         "expect": ["package_scope_mismatch", "registry_mismatch"],
         "mutate": _mutate_wrong_scope_registry},
        {"id": "7", "name": "package_mutator_after_candidate_hash",
         "expect": ["package_mutated_after_candidate_hash"],
         "mutate": _mutate_mutator_after_hash},
        {"id": "8", "name": "receipt_write_root_mismatch",
         "expect": ["receipt_write_root_set_mismatch"],
         "mutate": _mutate_write_root_mismatch},
    ]

def simulate_install(roots, decision, selected, fail_on=None):
    """Fixture-only installer simulation; never touches real roots."""
    report = {"written": [], "rolled_back": [], "skipped": [], "status": "not_applied"}
    if decision["decision"] != "APPROVED":
        report["skipped"] = sorted(roots)
        report["status"] = "fail_closed_zero_write"
        return report
    try:
        for name in selected:
            if fail_on == name:
                raise RuntimeError("simulated_write_failure")
            payload = json.dumps({"target_root": name, "bound": "root-selection-receipt"}, sort_keys=True)
            (roots[name] / "installed.json").write_text(payload, encoding="utf-8")
            report["written"].append(name)
        report["status"] = "applied"
    except RuntimeError:
        for name in report["written"]:
            for child in roots[name].iterdir():
                child.unlink()
        report["rolled_back"] = list(report["written"])
        report["written"] = []
        report["status"] = "partial_write_rolled_back"
    return report

def root_file_counts(roots):
    return {name: len(list(path.iterdir())) for name, path in roots.items()}


def evaluate_install_release_boundary(red_mode: bool = False) -> dict:
    failures: list = []
    findings: list = []
    evidence: dict = {"mode": "red" if red_mode else "green"}
    with tempfile.TemporaryDirectory(prefix="court-install-boundary-") as tmp:
        base = Path(tmp)
        roots, receipt, proofs, plan = build_fixture(base)
        evaluator = evaluate_root_write_plan_legacy_stub if red_mode else evaluate_root_write_plan_strict
        scenarios = build_scenarios()
        scenario_results = []
        for case in scenarios:
            mutated_receipt, mutated_proofs, mutated_plan = case["mutate"](
                deepcopy(receipt), deepcopy(proofs), deepcopy(plan))
            decision = evaluator(mutated_receipt, mutated_proofs, mutated_plan)
            rejected = decision["decision"] == "REJECTED"
            reason_ok = any(
                expected in reason
                for expected in case["expect"]
                for reason in decision["rejections"]
            )
            scenario_results.append({"id": case["id"], "name": case["name"],
                                     "rejected": rejected, "rejections": decision["rejections"]})
            if red_mode:
                if rejected:
                    failures.append("red_baseline_unexpected_rejection:" + case["id"])
                else:
                    findings.append("RED_" + case["id"] + "_" + case["name"] + "_unprotected")
            else:
                if not rejected:
                    failures.append("scenario_not_rejected:" + case["id"] + ":" + case["name"])
                elif not reason_ok:
                    failures.append("scenario_reason_mismatch:" + case["id"] + ":" + str(decision["rejections"]))
        evidence["scenarios"] = scenario_results
        if red_mode:
            evidence["red_findings"] = findings
            baseline_ok = not failures and len(findings) == len(scenarios)
            return {
                "schema": SCHEMA,
                "ok": False,
                "status": "RED_BASELINE" if baseline_ok else "FAIL",
                "contract": CONTRACT,
                "failures": failures,
                "findings": findings,
                "evidence": evidence,
            }
        selected = list(receipt["selected_roots"])
        proofless_receipt, proofless_proofs, proofless_plan = _mutate_provenance_missing(
            deepcopy(receipt), deepcopy(proofs), deepcopy(plan))
        proofless_decision = evaluate_root_write_plan_strict(
            proofless_receipt, proofless_proofs, proofless_plan)
        if proofless_decision["decision"] != "REJECTED":
            failures.append("proofless_root_not_rejected")
        counts_before = root_file_counts(roots)
        report_denied = simulate_install(roots, proofless_decision, selected)
        counts_after = root_file_counts(roots)
        if report_denied["status"] != "fail_closed_zero_write" or counts_before != counts_after:
            failures.append("zero_write_fail_closed_demo_failed")
        evidence["zero_write_fail_closed_demo"] = {
            "decision": proofless_decision["decision"],
            "rejections": proofless_decision["rejections"],
            "report": report_denied,
            "counts_before": counts_before,
            "counts_after": counts_after,
        }
        counts_before_rb = root_file_counts(roots)
        report_partial = simulate_install(
            roots, {"decision": "APPROVED"}, selected, fail_on=selected[-1])
        counts_after_rb = root_file_counts(roots)
        if (report_partial["status"] != "partial_write_rolled_back"
                or report_partial["rolled_back"] != [selected[0]]
                or counts_after_rb != counts_before_rb):
            failures.append("rollback_demo_failed")
        report_full = simulate_install(roots, {"decision": "APPROVED"}, selected)
        if (report_full["status"] != "applied"
                or sorted(report_full["written"]) != sorted(selected)):
            failures.append("fixture_apply_demo_failed")
        evidence["install_simulation_demo"] = {
            "rollback": report_partial, "applied": report_full}
        result = {
            "schema": SCHEMA,
            "ok": not failures,
            "status": "PASS" if not failures else "FAIL",
            "contract": CONTRACT,
            "failures": failures,
            "findings": findings,
            "evidence": evidence,
        }
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="install/release boundary check")
    parser.add_argument("--red", action="store_true",
                        help="replay RED baseline against legacy permissive stub")
    parser.add_argument("--json", action="store_true",
                        help="emit full JSON evidence")
    args = parser.parse_args()
    result = evaluate_install_release_boundary(red_mode=args.red)
    print(CONTRACT + "=" + result["status"])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for failure in result.get("failures") or []:
            print("FAILURE: " + str(failure))
        for finding in result.get("findings") or []:
            print("FINDING: " + str(finding))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

