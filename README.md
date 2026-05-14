# MetaResearch

Small Python toolkit for collecting and normalizing literature metadata for downstream research workflows.

This repo currently centers on a PubMed connector built on top of Biopython's `Entrez` client. It can:

- search PubMed and return PMIDs
- fetch normalized article records
- fetch PMC full text when a PubMed article has a linked PMC record
- append unseen PubMed results to a JSONL dataset

The `sleep/` folder is intentionally not documented here yet.

## Current layout

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

## Install

This project targets Python 3.13+.

```bash
uv sync
```

If you are not using `uv`, install the package and dev dependencies manually:

```bash
pip install -e .
pip install pytest
```

## PubMed usage

NCBI requires an email for Entrez requests. An API key is optional, and can be passed directly or through `NCBI_API_KEY`.

```python
from metaresearch.connectors.pubmed.PubMedConnector import PubMedConnector

connector = PubMedConnector(
    email="you@example.com",
    api_key=None,
)

pmids = connector.search("sleep deprivation AND cognition", max_results=5)
records = list(connector.fetch_records(pmids))

for record in records:
    print(record.source_id, record.title)
```

To append only new PubMed results to a JSONL file:

```python
written = connector.search_and_store_jsonl(
    "sleep deprivation AND cognition",
    "data/pubmed.jsonl",
    max_results=100,
)
print(written)
```

Each normalized record is represented by `RawRecord`, which includes fields such as:

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

## Status

The package structure suggests a broader literature-ingestion and meta-research workflow, but only the PubMed connector is implemented in a meaningful way right now. `main.py` is still a placeholder entry point.
