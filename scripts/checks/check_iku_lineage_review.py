"""Isolated development regressions for review identity and public projections."""
from __future__ import annotations

import json
import io
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive_checkpoint
import court_public_api as public
import iku_candidates as detector
import rebuild_shiguan_index as rebuild
import repair_archive_placeholders as repair
from shiguan_entry_utils import enrich_entry, load_entries, content_lineage_parts

LEGACY = "SUIKUIKUIKUIKUIKU17-20260101-1-ABAA"
VALID = "SDMLTIUW7-20260101-2-ABAA"
LINEAGE = "史馆总纪·典章志·记忆门·实录纲·索引目·关键词条·探测诏"
REVIEW_LINEAGE = "史馆总纪·待审志·待审门·待审纲·待审目·待审条·探测诏"


def record(code: str, lineage: str, receipt: bool = True, path: Path | None = None) -> str:
    receipt_line = ""
    if receipt and path is not None:
        entry = {"court_code": code, "lineage_display": lineage, "ancient_lineage": lineage, "time": "2026-01-01T00:00:00Z"}
        with patch.object(archive_checkpoint, "relative_to_data", return_value=path.relative_to(path.parent.parent.parent).as_posix()):
            payload = archive_checkpoint.build_archive_receipt(path, entry, {})
        receipt_line = "- archive_receipt_json: " + json.dumps(payload, ensure_ascii=False) + "\n"
    return (
        "## Checkpoint: Done\n- time: 2026-01-01T00:00:00Z\n- status: DONE\n"
        "- summary: isolatedprobe\n"
        f"- court_code: {code}\n- ancient_lineage: {lineage}\n"
        + receipt_line
        + "诏令编号：［IKU］ 待 archive_checkpoint 生成\n"
    )


class ReviewIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "shared" / "references" / "plan-archives"
        self.root.mkdir(parents=True)

    def test_new_review_code_is_explicit_and_classified_case_still_works(self) -> None:
        item = enrich_entry({"topic": "未命名新课题", "summary": "新型未知领域"})
        self.assertEqual(item["classification_status"], "review")
        self.assertEqual(item["classification_reason"], "unknown")
        self.assertTrue(item["court_code"].startswith("SREVIEWU"))
        self.assertNotIn("UIKUIK", item["court_code"])
        classified = enrich_entry({"topic": "史馆实录索引与生长树", "summary": "史馆 archive index keyword"})
        self.assertEqual(classified["classification_status"], "classified")
        self.assertFalse(classified["court_code_review_required"])

    def test_valid_historical_identity_and_classification_are_preserved(self) -> None:
        parts = content_lineage_parts({"topic": "史馆实录索引与生长树", "summary": "史馆 archive index keyword"})
        item = enrich_entry({"topic": "未命名新课题", "time": "2026-09-06T00:00:00Z", "court_code": VALID, "lineage_parts": parts})
        self.assertEqual(item["court_code"], VALID)
        self.assertEqual(item["lineage_parts"], parts)
        self.assertEqual(item["classification_status"], "classified")
        self.assertEqual(item["court_code_parts"]["date"], "20260101")
        self.assertEqual(item["court_code_parts"]["sequence"], "2")

    def test_historical_display_rebuild_both_public_queries_and_receipt(self) -> None:
        path = self.root / "probe-20260101.md"
        path.write_text("# Archive: isolatedprobe\n" + record(LEGACY, REVIEW_LINEAGE, path=path), encoding="utf-8")
        before = path.read_bytes()
        with patch.object(rebuild, "relative", return_value="references/plan-archives/probe.md"):
            item = rebuild.parse_archive(path)[0]
        self.assertEqual(item["court_code"], LEGACY)
        self.assertEqual(item["lineage_display"], REVIEW_LINEAGE)
        self.assertEqual(item["classification_status"], "review")
        self.assertEqual(item["classification_reason"], "stored_review_lineage")
        self.assertEqual(item["court_code_parts"]["lineage"], LEGACY.split("-")[0])
        index = self.root.parent / "shiguan-index.jsonl"
        other = {"topic": "differenttopic", "summary": "unrelatedsubject", "time": "2025-01-01T00:00:00Z"}
        index.write_text("\n".join(json.dumps(value, ensure_ascii=False) for value in (item, other)) + "\n", encoding="utf-8")
        with patch.object(public, "load_entries", side_effect=lambda: load_entries(index)):
            full = public.shiguan_query(terms=[])["stdout"][0]
            compact = public.public_shiguan_entries_query("isolatedprobe")["matches"][0]
        for projection in (full, compact):
            self.assertEqual(projection["court_code"], LEGACY)
            self.assertEqual(projection["classification_status"], "review")
            self.assertTrue(projection["court_code_review_required"])
        with patch.object(archive_checkpoint, "relative_to_data", return_value="references/plan-archives/probe.md"):
            receipt = archive_checkpoint.build_archive_receipt(path, item, {})
        self.assertEqual(receipt["court_code"], LEGACY)
        self.assertEqual(receipt["classification_status"], "review")
        self.assertEqual(path.read_bytes(), before)

    def test_legacy_candidates_review_and_never_become_refill_source(self) -> None:
        path = self.root / "legacy.md"
        path.write_text(record(LEGACY, REVIEW_LINEAGE, path=path), encoding="utf-8")
        before = path.read_bytes()
        with patch.object(detector, "archive_root", return_value=self.root):
            result = public.public_iku_candidates()
        candidates = result["candidates"]
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(candidate["suggested_action"] == "REVIEW" for candidate in candidates))
        self.assertIn("LEGACY_REVIEW_CODE", {candidate["placeholder_kind"] for candidate in candidates})
        self.assertEqual(repair.plan_repairs(root=self.root), [])
        self.assertEqual(path.read_bytes(), before)
        self.assertIsNone(detector.placeholder_kind("- court_code: SAIKUB-20260101-1-ABAA"))
        self.assertEqual(detector.suggest_action("LEGACY_REVIEW_CODE", "正文", None, None, None)[0], "NOOP")

    def test_placeholder_wording_does_not_supply_receipt(self) -> None:
        (self.root / "no-receipt.md").write_text(record(VALID, LINEAGE, receipt=False), encoding="utf-8")
        self.assertEqual(detector.detect_candidates(root=self.root)[0]["suggested_action"], "REVIEW")
        self.assertEqual(repair.plan_repairs(root=self.root), [])

    def test_checkpoint_sources_and_duplicate_references_stay_bound_to_coordinates(self) -> None:
        path = self.root / "multi.md"
        path.write_text(record(LEGACY, REVIEW_LINEAGE, path=path) + record(VALID, LINEAGE, path=path), encoding="utf-8")
        plan = repair.plan_repairs(root=self.root)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["nearest_court_code"], VALID)
        original = path.read_bytes()
        result = repair.apply_repairs(plan, root=self.root, backup_root=self.root.parent / "backups", yes=True)
        self.assertEqual(result["replacements"], 1)
        text = path.read_text(encoding="utf-8")
        self.assertIn("诏令编号：［IKU］", text.split("## Checkpoint: Done")[1])
        self.assertIn(f"诏令编号：{VALID}", text.split("## Checkpoint: Done")[2])
        self.assertEqual(repair.plan_repairs(root=self.root), [])
        journal = json.loads(Path(result["journal_path"]).read_text(encoding="utf-8"))
        backup = Path(journal["files"][0]["backup_path"])
        self.assertEqual(backup.read_bytes(), original)
        repair.rollback(backup, path)
        self.assertEqual(path.read_bytes(), original)

    def test_conflicting_metadata_source_is_review(self) -> None:
        path = self.root / "conflict.md"
        text = record(VALID, LINEAGE, path=path).replace("诏令编号：", f"- court_code: {LEGACY}\n诏令编号：")
        path.write_text(text, encoding="utf-8")
        self.assertEqual(repair.plan_repairs(root=self.root), [])

    def test_stale_source_is_refused_without_writing(self) -> None:
        path = self.root / "stale.md"
        path.write_text(record(VALID, LINEAGE, path=path), encoding="utf-8")
        plan = repair.plan_repairs(root=self.root)
        path.write_text(record(LEGACY, REVIEW_LINEAGE, path=path), encoding="utf-8")
        changed = path.read_bytes()
        backups = self.root.parent / "backups"
        with self.assertRaisesRegex(ValueError, "repair_plan_source_changed"):
            repair.apply_repairs(plan, root=self.root, backup_root=backups, yes=True)
        self.assertEqual(path.read_bytes(), changed)
        self.assertFalse(backups.exists())

    def test_concurrent_beforeimage_change_is_refused(self) -> None:
        path = self.root / "concurrent.md"
        path.write_text(record(VALID, LINEAGE, path=path), encoding="utf-8")
        plan = repair.plan_repairs(root=self.root)
        write_backup = repair._atomic_write_bytes
        concurrent = b"concurrent writer content\n"

        def change_after_backup(target: Path, data: bytes) -> None:
            write_backup(target, data)
            path.write_bytes(concurrent)

        with patch.object(repair, "_atomic_write_bytes", side_effect=change_after_backup):
            with self.assertRaisesRegex(ValueError, "repair_beforeimage_changed"):
                repair.apply_repairs(plan, root=self.root, backup_root=self.root.parent / "backups", yes=True)
        self.assertEqual(path.read_bytes(), concurrent)

    def test_two_valid_checkpoint_placeholders_both_repair(self) -> None:
        path = self.root / "both.md"
        second = "SDMLTIUW7-20260101-3-ABAA"
        path.write_text(record(VALID, LINEAGE, path=path) + record(second, LINEAGE, path=path), encoding="utf-8")
        plan = repair.plan_repairs(root=self.root)
        self.assertEqual(len(plan), 2)
        result = repair.apply_repairs(plan, root=self.root, backup_root=self.root.parent / "backups", yes=True)
        self.assertEqual(result["replacements"], 2)
        text = path.read_text(encoding="utf-8")
        self.assertIn(f"诏令编号：{VALID}", text)
        self.assertIn(f"诏令编号：{second}", text)
        journal = json.loads(Path(result["journal_path"]).read_text(encoding="utf-8"))
        replacements = journal["files"][0]["replacements"]
        self.assertIsNone(journal["files"][0]["nearest_court_code"])
        self.assertEqual([item["nearest_court_code"] for item in replacements], [VALID, second])
        self.assertEqual([item["receipt_hint"] for item in replacements], [f"shiguan:{VALID}", f"shiguan:{second}"])
        self.assertNotEqual(replacements[0]["checkpoint_line_number"], replacements[1]["checkpoint_line_number"])

    def test_source_change_after_replanning_is_refused(self) -> None:
        path = self.root / "race.md"
        path.write_text(record(VALID, LINEAGE, path=path), encoding="utf-8")
        plan = repair.plan_repairs(root=self.root)
        real_plan = repair.plan_repairs
        changed = record(LEGACY, REVIEW_LINEAGE, path=path).encode("utf-8")

        def mutate_after_plan(*args, **kwargs):
            result = real_plan(*args, **kwargs)
            path.write_bytes(changed)
            return result

        with patch.object(repair, "plan_repairs", side_effect=mutate_after_plan):
            with self.assertRaisesRegex(ValueError, "repair_plan_source_changed"):
                repair.apply_repairs(plan, root=self.root, backup_root=self.root.parent / "backups", yes=True)
        self.assertEqual(path.read_bytes(), changed)

    def test_partial_failure_keeps_journal_and_each_beforeimage(self) -> None:
        first, second = self.root / "a.md", self.root / "b.md"
        for path in (first, second):
            path.write_text(record(VALID, LINEAGE, path=path), encoding="utf-8")
        originals = {path.name: path.read_bytes() for path in (first, second)}
        plan = repair.plan_repairs(root=self.root)
        writer = repair.atomic_write_text
        backups = self.root.parent / "backups"

        def fail_second(path, *args, **kwargs):
            if Path(path) == second:
                raise OSError("injected second write failure")
            return writer(path, *args, **kwargs)

        with patch.object(repair, "atomic_write_text", side_effect=fail_second):
            with self.assertRaises(OSError):
                repair.apply_repairs(plan, root=self.root, backup_root=backups, yes=True)
        journal = json.loads(next(backups.glob("repair-journal-*.json")).read_text(encoding="utf-8"))
        self.assertEqual([item["write_status"] for item in journal["files"]], ["APPLIED", "FAILED"])
        for item in journal["files"]:
            self.assertEqual(Path(item["backup_path"]).read_bytes(), originals[Path(item["record_path"]).name])
        self.assertEqual(second.read_bytes(), originals[second.name])

    def test_receipt_keyword_and_wrong_checkpoint_receipt_are_review(self) -> None:
        path = self.root / "receipt.md"
        text = record(VALID, LINEAGE, receipt=False) + "- receipt: not_archive_checkpoint\n"
        path.write_text(text, encoding="utf-8")
        self.assertEqual(repair.plan_repairs(root=self.root), [])
        path.write_text(record(VALID, LINEAGE, path=self.root / "other.md"), encoding="utf-8")
        self.assertEqual(repair.plan_repairs(root=self.root), [])

    def test_metadata_prefixes_are_preserved(self) -> None:
        path = self.root / "metadata.md"
        text = record(VALID, LINEAGE, path=path)
        text = text.replace(f"- court_code: {VALID}", "- court_code: IKU")
        text = text.replace(f"- ancient_lineage: {LINEAGE}", "- ancient_lineage: IKU")
        text += "- lineage_display: IKU\n"
        path.write_text(text, encoding="utf-8")
        result = repair.apply_repairs(repair.plan_repairs(root=self.root), root=self.root, backup_root=self.root.parent / "backups", yes=True)
        self.assertEqual(result["replacements"], 4)
        output = path.read_text(encoding="utf-8")
        self.assertIn(f"- court_code: {VALID}", output)
        self.assertIn(f"- ancient_lineage: {LINEAGE}", output)
        self.assertIn(f"- lineage_display: {LINEAGE}", output)

    def test_production_archive_embeds_bound_receipt(self) -> None:
        path = self.root / "produced.md"
        with ExitStack() as stack:
            stack.enter_context(patch.object(archive_checkpoint, "archive_path", return_value=path))
            stack.enter_context(patch.object(archive_checkpoint, "index_path", return_value=self.root.parent / "shiguan-index.jsonl"))
            stack.enter_context(patch.object(archive_checkpoint, "shiguan_write_lock_path", return_value=self.root.parent / "court-runtime" / "shiguan-write.lock"))
            stack.enter_context(patch.object(archive_checkpoint, "relative_to_data", side_effect=lambda value: value.relative_to(self.root.parent.parent).as_posix()))
            stack.enter_context(patch.object(archive_checkpoint, "ensure_shared_seed", return_value=None))
            stack.enter_context(redirect_stdout(io.StringIO()))
            code = archive_checkpoint.main([
                "--topic", "史馆实录索引与生长树", "--phase", "Done", "--status", "DONE",
                "--summary", "史馆 archive index keyword", "--evidence", "isolated fixture",
                "--next", "none", "--source-agent", "codex", "--memory-decision", "SKIP", "--no-refresh",
            ])
        self.assertEqual(code, 0)
        output = path.read_text(encoding="utf-8")
        self.assertIn("- archive_receipt_json:", output)
        path.write_text(output + "诏令编号：［IKU］ 待 archive_checkpoint 生成\n", encoding="utf-8")
        self.assertEqual(len(repair.plan_repairs(root=self.root)), 1)

    def test_transaction_backups_are_unique_and_old_rollback_still_works(self) -> None:
        path = self.root / "unique.md"
        path.write_text(record(VALID, LINEAGE, path=path), encoding="utf-8")
        original = path.read_bytes()
        backups = self.root.parent / "backups"
        journals = []
        for _ in range(2):
            result = repair.apply_repairs(repair.plan_repairs(root=self.root), root=self.root, backup_root=backups, yes=True)
            journals.append(json.loads(Path(result["journal_path"]).read_text(encoding="utf-8")))
            repair.rollback(Path(journals[-1]["files"][0]["backup_path"]), path)
            self.assertEqual(path.read_bytes(), original)
        self.assertNotEqual(journals[0]["journal_path"], journals[1]["journal_path"])
        self.assertNotEqual(journals[0]["files"][0]["backup_path"], journals[1]["files"][0]["backup_path"])
        # Rollback remains compatible with an existing binary .bak, without
        # requiring any new journal fields or recomputing a content fingerprint.
        old_backup = backups / "historical.bak"
        old_backup.write_bytes(original)
        repair.rollback(old_backup, path)
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
