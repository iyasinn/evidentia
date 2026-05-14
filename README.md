# MetaResearch

Research tooling is still weirdly manual.

MetaResearch is a small Python project for turning messy literature search into structured, reusable research data. The current focus is PubMed ingestion, but the real direction is larger: a foundation for search, extraction, synthesis, and eventually meta-analysis workflows that do not collapse into spreadsheet chaos.

## Why this exists

Most research workflows still look like this:

- search for papers
- click through inconsistent records
- copy metadata by hand
- lose track of what has already been collected
- rebuild the same dataset every time a question changes

MetaResearch starts by fixing the ingestion layer.

Right now it gives you a clean PubMed connector that can:

- search PubMed and return PMIDs
- fetch normalized article records
- fetch PMC full text when available
- append only unseen results to a JSONL dataset

That sounds small, but it is the piece everything else depends on.

## What is in the repo

The current codebase is intentionally narrow.

```text
.
├── main.py
├── pyproject.toml
├── src/metaresearch/
│   └── connectors/
│       ├── LiteratureConnector.py
│       └── pubmed/PubMedConnector.py
└── tests/
    └── connectors/pubmed/
```

The `sleep/` work is not part of this README yet.

## Quick start

This project targets Python 3.13+.

```bash
uv sync
```

If you are not using `uv`:

```bash
pip install -e .
pip install pytest
```

NCBI requires an email for Entrez requests. You can also provide an API key directly or through `NCBI_API_KEY`.

```python
from metaresearch.connectors.pubmed.PubMedConnector import PubMedConnector

connector = PubMedConnector(email="you@example.com")

pmids = connector.search("sleep deprivation AND cognition", max_results=5)
records = list(connector.fetch_records(pmids))

for record in records:
    print(record.source_id, record.title)
```

If you want a dataset you can keep growing without duplicating rows:

```python
written = connector.search_and_store_jsonl(
    "sleep deprivation AND cognition",
    "data/pubmed.jsonl",
    max_results=100,
)
print(f"wrote {written} new records")
```

## Data model

Records are normalized into a shared `RawRecord` shape so downstream code does not need to care where the paper came from.

Typical fields include:

- `source`
- `source_id`
- `title`
- `abstract`
- `authors`
- `journal`
- `publication_date`
- `doi`
- `affiliations`
- `keywords`
- `publication_types`
- `raw`

## Tests

```bash
pytest tests/connectors/pubmed/test_pubmed_connector.py
```

## Direction

This is not meant to stop at “PubMed wrapper.”

The broader idea is a research stack that can move from:

- ingestion
- retrieval
- extraction
- synthesis
- meta-analysis

The current implementation is just the first layer, but it is the right first layer: reliable, structured paper intake.
