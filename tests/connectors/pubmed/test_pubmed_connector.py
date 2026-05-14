from __future__ import annotations

import io
import importlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

from metaresearch.connectors.LiteratureConnector import RawRecord

connector_module = importlib.import_module("metaresearch.connectors.pubmed.PubMedConnector")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class PubMedConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entrez = Mock()
        self.entrez_patch = patch.object(
            connector_module,
            "EntrezModule",
            self.entrez,
        )
        self.entrez_patch.start()
        self.addCleanup(self.entrez_patch.stop)

        self.connector = connector_module.PubMedConnector(
            email="reader@example.com",
            api_key="test-key",
            tool="MetaResearchTests",
        )

    def test_search_returns_pubmed_ids(self) -> None:
        self.entrez.esearch.return_value = _text_handle("search")
        self.entrez.read.return_value = {"IdList": ["101", "202"]}

        pmids = self.connector.search("asthma", max_results=2)

        self.assertEqual(pmids, ["101", "202"])

    def test_fetch_records_parses_complete_pubmed_article(self) -> None:
        with patch.object(
            self.connector,
            "_fetch_pubmed_articles",
            return_value=[_pubmed_article_from_fixture("pubmed_article_complete.xml")],
        ):
            records = list(self.connector.fetch_records(["12345"]))

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source_id, "12345")
        self.assertEqual(record.title, "Effects of readable tests on connector quality")
        self.assertTrue(record.abstract.startswith("BACKGROUND: Background section text."))
        self.assertEqual(record.journal, "Journal of Testing")
        self.assertEqual(record.publication_date, date(2024, 3, 15))
        self.assertEqual(record.doi, "10.1000/test-doi")
        self.assertIn("Jane Doe", record.authors)
        self.assertIn("John Smith", record.authors)
        self.assertIn("Readability", record.keywords)
        self.assertIn("Clinical Trials as Topic", record.keywords)
        self.assertIn("Journal Article", record.publication_types)

    def test_fetch_records_handles_sparse_metadata_without_crashing(self) -> None:
        with patch.object(
            self.connector,
            "_fetch_pubmed_articles",
            return_value=[_pubmed_article_from_fixture("pubmed_article_sparse.xml")],
        ):
            records = list(self.connector.fetch_records(["67890"]))

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source_id, "67890")
        self.assertEqual(record.title, "Consortium findings without an abstract")
        self.assertIsNone(record.abstract)
        self.assertEqual(record.publication_date, date(2021, 1, 1))
        self.assertEqual(record.doi, "10.2000/sparse-doi")
        self.assertIn("MetaResearch Consortium", record.authors)
        self.assertIn("Publishing", record.keywords)

    def test_fetch_full_text_returns_none_without_pmc_link(self) -> None:
        with patch.object(self.connector, "_lookup_pmc_id", return_value=None):
            full_text = self.connector.fetch_full_text("12345")

        self.assertIsNone(full_text)

    def test_fetch_full_text_returns_body_text_when_pmc_xml_exists(self) -> None:
        pmc_root = ET.fromstring(_fixture_bytes("pmc_full_text.xml"))

        with patch.object(self.connector, "_lookup_pmc_id", return_value="PMC123"), patch.object(
            self.connector,
            "_fetch_xml",
            return_value=pmc_root,
        ):
            full_text = self.connector.fetch_full_text("12345")

        self.assertEqual(full_text, "Introduction First paragraph. Second paragraph.")

    def test_search_and_store_jsonl_appends_only_unseen_pmids(self) -> None:
        existing_record = {
            "pmid": "100",
            "source_id": "100",
            "title": "Already stored",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "pubmed.jsonl"
            output_path.write_text(json.dumps(existing_record) + "\n", encoding="utf-8")

            with patch.object(
                self.connector,
                "search",
                return_value=["100", "200", "200", "300"],
            ), patch.object(
                self.connector,
                "fetch_records",
                return_value=iter(
                    [
                        _sample_record("200", "New record one"),
                        _sample_record("300", "New record two"),
                    ]
                ),
            ):
                written = self.connector.search_and_store_jsonl(
                    "test query",
                    output_path,
                    max_results=10,
                )

            self.assertEqual(written, 2)
            stored_rows = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([row["pmid"] for row in stored_rows], ["100", "200", "300"])
            self.assertEqual(stored_rows[1]["publication_date"], "2024-01-01")


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def _pubmed_article_from_fixture(name: str) -> ET.Element:
    root = ET.fromstring(_fixture_bytes(name))
    return root.find("./PubmedArticle")


def _sample_record(pmid: str, title: str) -> RawRecord:
    return RawRecord(
        source="pubmed",
        source_id=pmid,
        title=title,
        abstract=None,
        publication_date=date(2024, 1, 1),
    )


def _text_handle(value: str) -> Mock:
    handle = Mock()
    handle.__enter__ = Mock(return_value=io.StringIO(value))
    handle.__exit__ = Mock(return_value=None)
    return handle


if __name__ == "__main__":
    unittest.main()
