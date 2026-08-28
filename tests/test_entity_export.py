import csv
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from entity.resolver import EntityResolver, normalize_name
from exporter import export_csv, export_required_tabs
from models.schemas import EntityMapping

class EntityExportTests(unittest.TestCase):
    def test_resolution_and_no_match(self) -> None:
        resolver = EntityResolver({"OpenAI": ["Open AI"]})
        self.assertEqual(normalize_name("OpenAI, Inc."), "openai")
        self.assertEqual(resolver.resolve("Open AI").canonical_name, "OpenAI")
        self.assertIsNone(resolver.resolve("Unrelated Systems").canonical_name)

    def test_csv_export(self) -> None:
        output = Path("data/export/test.csv")
        export_csv([EntityMapping(raw_name="OpenAI", normalized_name="openai", canonical_name="OpenAI", match_method="exact", confidence=1, timestamp=datetime.now(UTC))], output)
        with output.open() as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 1)
        output.unlink()

    def test_required_tab_files(self) -> None:
        directory = Path("data/export/tabs")
        export_required_tabs({}, directory)
        self.assertEqual(len(list(directory.glob("*.csv"))), 6)
        for path in directory.glob("*.csv"):
            path.unlink()
        directory.rmdir()
