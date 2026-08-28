import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from extractors.paper import extract_authors, extract_published_date, extract_title, find_github_url, has_paperswithcode_evidence
from models.schemas import PaperContent, ResearchPaper, Source
from paper_collector import paper_identity

HTML = """<meta name='citation_date' content='2017-06-12'><h1 class='title'>Title: Attention Is All You Need</h1><div class='authors'><a>Ashish Vaswani</a><a>Noam Shazeer</a></div><a href='https://github.com/tensorflow/tensor2tensor'>Code</a>"""

class PaperPhaseOneTests(unittest.TestCase):
    def test_arxiv_markup_extraction(self) -> None:
        self.assertEqual(extract_title(HTML), "Attention Is All You Need")
        self.assertEqual(extract_authors(HTML), ["Ashish Vaswani", "Noam Shazeer"])
        self.assertEqual(extract_published_date(HTML), "2017-06-12T00:00:00+00:00")
        self.assertEqual(find_github_url(HTML), "https://github.com/tensorflow/tensor2tensor")
        self.assertEqual(extract_published_date("<div class='dateline'>Submitted on 12 Jun 2017</div>"), "2017-06-12T00:00:00+00:00")
        self.assertEqual(extract_published_date("<meta name='citation_date' content='2017/06/12'>"), "2017-06-12T00:00:00+00:00")

    def test_no_github_is_not_invented(self) -> None:
        self.assertIsNone(find_github_url("<a href='https://example.com/project'>Project</a>"))
        self.assertFalse(has_paperswithcode_evidence("<title>Unrelated page</title>"))

    def test_schema_and_arxiv_deduplication_identity(self) -> None:
        def make_paper(url: str) -> ResearchPaper:
            return ResearchPaper(source=Source(name="arXiv", url=url), content=PaperContent(title="Example", paper_url=url), collectedAt=datetime.now(UTC))
        self.assertEqual(paper_identity(make_paper("https://arxiv.org/abs/1706.03762")), paper_identity(make_paper("https://arxiv.org/abs/1706.03762v5")))

    def test_invalid_empty_title_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PaperContent(title="", paper_url="https://arxiv.org/abs/1706.03762")
