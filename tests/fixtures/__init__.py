"""Test fixtures generator for deterministic testing."""
from pathlib import Path

fixtures = Path(__file__).parent

(fixtures / "arxiv_sample.html").write_text("""<!DOCTYPE html>
<html>
<head>
  <meta name="citation_title" content="Attention Is All You Need">
  <meta name="citation_author" content="Ashish Vaswani">
  <meta name="citation_author" content="Noam Shazeer">
  <meta name="citation_date" content="2017-06-12">
</head>
<body>
  <h1 class="title">Attention Is All You Need</h1>
  <div class="authors">
    <a href="#">Ashish Vaswani</a>
    <a href="#">Noam Shazeer</a>
  </div>
  <a href="https://github.com/tensorflow/tensor2tensor">Source Repository</a>
</body>
</html>""", encoding="utf-8")

(fixtures / "paperswithcode_sample.html").write_text("""<!DOCTYPE html>
<html>
<head>
  <meta property="og:site_name" content="Papers With Code">
  <meta name="citation_title" content="LoRA: Low-Rank Adaptation of Large Language Models">
  <meta name="citation_author" content="Edward J. Hu">
  <meta name="citation_author" content="Yelong Shen">
  <meta name="citation_date" content="2021-06-17">
</head>
<body>
  <h1 class="paper-title">LoRA: Low-Rank Adaptation of Large Language Models</h1>
  <a href="https://arxiv.org/abs/2106.09685">arXiv Page</a>
  <a href="https://github.com/microsoft/LoRA">GitHub Code</a>
</body>
</html>""", encoding="utf-8")

(fixtures / "paperswithcode_api.json").write_text("""{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "lora-low-rank-adaptation-of-large-language",
      "title": "LoRA: Low-Rank Adaptation of Large Language Models",
      "authors": ["Edward J. Hu", "Yelong Shen"],
      "published": "2021-06-17",
      "url_abs": "https://arxiv.org/abs/2106.09685",
      "paper_url": "https://paperswithcode.com/paper/lora-low-rank-adaptation-of-large-language"
    },
    {
      "id": "qlora-efficient-finetuning-of-quantized-llms",
      "title": "QLoRA: Efficient Finetuning of Quantized LLMs",
      "authors": ["Tim Dettmers", "Artidoro Pagnoni"],
      "published": "2023-05-23",
      "url_abs": "https://arxiv.org/abs/2305.14314",
      "paper_url": "https://paperswithcode.com/paper/qlora-efficient-finetuning-of-quantized-llms"
    }
  ]
}""", encoding="utf-8")

(fixtures / "venture_startup.html").write_text("""<!DOCTYPE html>
<html>
<head>
  <meta property="og:site_name" content="Acme AI Innovations, Inc.">
  <title>About Acme AI</title>
</head>
<body>
  <h1>About Acme AI</h1>
  <p>Acme AI builds enterprise neural solutions. We are a passionate team of over 250 employees based in San Francisco.</p>
</body>
</html>""", encoding="utf-8")

(fixtures / "venture_product.html").write_text("""<!DOCTYPE html>
<html>
<head>
  <meta property="og:title" content="Acme Neural Cloud">
  <title>Pricing - Acme Neural Cloud</title>
</head>
<body>
  <h1>Acme Neural Cloud Pricing</h1>
  <p>Get started with flexible custom pricing. Enterprise plans are tailored for scale; contact sales for volume discounts.</p>
</body>
</html>""", encoding="utf-8")

(fixtures / "news_article.html").write_text("""<!DOCTYPE html>
<html>
<head>
  <meta property="og:title" content="New Frontier Model Breakthrough Announced">
  <meta property="article:published_time" content="2026-08-28T09:00:00Z">
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    "headline": "New Frontier Model Breakthrough Announced",
    "datePublished": "2026-08-28T09:00:00Z"
  }
  </script>
</head>
<body>
  <article>
    <h1>New Frontier Model Breakthrough Announced</h1>
    <p>Researchers today released a major update to frontier models, improving computational reasoning across standard benchmarks.</p>
  </article>
</body>
</html>""", encoding="utf-8")

(fixtures / "job_posting.html").write_text("""<!DOCTYPE html>
<html>
<head>
  <meta property="og:title" content="Senior AI Research Scientist (Remote)">
  <meta name="date" content="2026-08-28T08:30:00Z">
</head>
<body>
  <h1>Senior AI Research Scientist (Remote)</h1>
  <p>We are hiring a remote research scientist to lead frontier foundation model evaluation.</p>
</body>
</html>""", encoding="utf-8")

if __name__ == "__main__":
    print("Fixtures generated successfully.")
