import csv
import json
import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from entity.resolver import EntityResolver, normalize_name
from exporter import export_csv, export_jsonl_files, export_required_tabs
from models.schemas import EntityMapping
from sheets_exporter import export_google_sheets, transform_records


class EntityExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seeds = {
            "OpenAI": ["Open AI", "OpenAI Inc", "OpenAI, Inc.", "OpenAI Incorporated"],
            "Google DeepMind": ["DeepMind", "DeepMind Technologies"],
            "Anthropic": ["Anthropic PBC"],
        }
        self.resolver = EntityResolver(self.seeds, fuzzy_threshold=0.92)

    def test_exact_entity_match(self) -> None:
        res = self.resolver.resolve("OpenAI")
        self.assertEqual(res.canonical_name, "OpenAI")
        self.assertEqual(res.match_method, "exact")
        self.assertEqual(res.confidence, 1.0)

    def test_alias_match(self) -> None:
        res = self.resolver.resolve("DeepMind")
        self.assertEqual(res.canonical_name, "Google DeepMind")
        self.assertEqual(res.match_method, "alias")
        self.assertEqual(res.confidence, 1.0)

    def test_legal_suffix_removal(self) -> None:
        self.assertEqual(normalize_name("OpenAI, Inc."), "openai")
        self.assertEqual(normalize_name("Anthropic PBC"), "anthropic")
        self.assertEqual(normalize_name("DeepMind Technologies Ltd"), "deepmind")
        res = self.resolver.resolve("OpenAI Incorporated")
        self.assertEqual(res.canonical_name, "OpenAI")

    def test_whitespace_and_case_differences(self) -> None:
        res = self.resolver.resolve("  open  ai  ")
        self.assertEqual(res.canonical_name, "OpenAI")
        self.assertEqual(res.confidence, 1.0)

    def test_conservative_fuzzy_match(self) -> None:
        resolver = EntityResolver({"Perplexity AI": []}, fuzzy_threshold=0.88)
        # Minor typo in long name
        res = resolver.resolve("Perplexity A.I.")
        self.assertEqual(res.canonical_name, "Perplexity AI")

    def test_unsafe_fuzzy_match_rejected(self) -> None:
        # OpenAI must never match OpenTable or OpenSource
        res = self.resolver.resolve("OpenTable")
        self.assertIsNone(res.canonical_name)
        self.assertEqual(res.match_method, "no_match")
        self.assertEqual(res.confidence, 0.0)

    def test_unresolved_entity_remains_unresolved(self) -> None:
        res = self.resolver.resolve("Completely Unknown Startup 12345")
        self.assertIsNone(res.canonical_name)
        self.assertEqual(res.match_method, "no_match")
        self.assertEqual(res.confidence, 0.0)

    def test_entity_mapping_jsonl_log(self) -> None:
        log_path = Path("data/output/test_mapping_log.jsonl")
        log_path.unlink(missing_ok=True)
        resolver = EntityResolver(self.seeds, mapping_log=log_path)
        resolver.resolve("Open AI", source_url="https://openai.com")
        self.assertTrue(log_path.exists())
        lines = log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data["raw_name"], "Open AI")
        self.assertEqual(data["canonical_name"], "OpenAI")
        log_path.unlink(missing_ok=True)

    def test_csv_export(self) -> None:
        output = Path("data/export/test_export.csv")
        export_csv(
            [
                EntityMapping(
                    raw_name="OpenAI",
                    normalized_name="openai",
                    canonical_name="OpenAI",
                    match_method="exact",
                    confidence=1.0,
                    timestamp=datetime.now(UTC),
                )
            ],
            output,
        )
        self.assertTrue(output.exists())
        with output.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["raw_name"], "OpenAI")
            self.assertEqual(rows[0]["canonical_name"], "OpenAI")
        output.unlink(missing_ok=True)

    def test_required_tab_files(self) -> None:
        directory = Path("data/export/test_tabs")
        export_required_tabs({}, directory)
        csv_files = list(directory.glob("*.csv"))
        self.assertEqual(len(csv_files), 6)
        for path in csv_files:
            path.unlink()
        directory.rmdir()

    def test_sheets_dry_run_generation(self) -> None:
        dry_run_path = Path("data/output/test_sheets_dry_run.json")
        dry_run_path.unlink(missing_ok=True)
        export_google_sheets({}, dry_run=True, output=dry_run_path)
        self.assertTrue(dry_run_path.exists())
        data = json.loads(dry_run_path.read_text(encoding="utf-8"))
        self.assertIn("Startups", data)
        self.assertIn("Products", data)
        self.assertIn("Research Papers", data)
        self.assertIn("Jobs", data)
        self.assertIn("News", data)
        self.assertIn("Entity Mapping Log", data)
        dry_run_path.unlink(missing_ok=True)

    def test_sheets_missing_credentials_raises_explicitly(self) -> None:
        old_env = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        try:
            if "GOOGLE_SERVICE_ACCOUNT_JSON" in os.environ:
                del os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_SERVICE_ACCOUNT_JSON is required"):
                export_google_sheets({}, dry_run=False)
        finally:
            if old_env is not None:
                os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = old_env
