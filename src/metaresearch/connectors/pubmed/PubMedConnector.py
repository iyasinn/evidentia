from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Sequence
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from Bio import Entrez as EntrezModule
else:
    try:
        from Bio import Entrez as EntrezModule
    except ModuleNotFoundError:
        EntrezModule = None

from metaresearch.connectors.LiteratureConnector import LiteratureConnector, RawRecord


class PubMedConnector(LiteratureConnector):
    """PubMed connector built on NCBI E-utilities via Biopython Entrez."""

    _MAX_FETCH_BATCH = 200

    def __init__(
        self,
        *,
        email: str,
        api_key: str | None = None,
        tool: str = "MetaResearch",
    ) -> None:
        if not email:
            raise ValueError("PubMedConnector requires an email for NCBI Entrez.")

        self._email = email
        self._api_key = api_key or os.getenv("NCBI_API_KEY")
        self._tool = tool

        if EntrezModule is not None:
            self._configure_entrez(EntrezModule)

    @property
    def source_name(self) -> str:
        return "pubmed"

    def search(self, query: str, max_results: int = 1000) -> list[str]:
        entrez = self._get_entrez()
        with entrez.esearch(
            db="pubmed",
            term=query,
            retmax=max_results,
            usehistory="n",
        ) as handle:
            payload = entrez.read(handle)
        return list(payload.get("IdList", []))

    def fetch_records(self, ids: Sequence[str]) -> Iterator[RawRecord]:
        for batch in _batched(ids, self._MAX_FETCH_BATCH):
            for article in self._fetch_pubmed_articles(batch):
                record = self._parse_pubmed_article(article)
                if record is not None:
                    yield record

    def fetch_full_text(self, source_id: str) -> str | None:
        pmc_id = self._lookup_pmc_id(source_id)
        if pmc_id is None:
            return None

        root = self._fetch_xml(db="pmc", ids=[pmc_id])
        body = root.find(".//body")
        if body is None:
            return None

        text = " ".join(part.strip() for part in body.itertext() if part.strip())
        return text or None

    def search_and_store_jsonl(
        self,
        query: str,
        output_path: str | Path,
        max_results: int = 1000,
    ) -> int:
        """Append only unseen PMIDs to a JSONL file and return records written."""
        output_file = Path(output_path)
        seen_pmids = _load_seen_pmids(output_file)
        candidate_ids = self.search(query, max_results=max_results)
        unseen_ids = list(dict.fromkeys(
            pmid for pmid in candidate_ids if pmid not in seen_pmids
        ))
        if not unseen_ids:
            return 0

        output_file.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with output_file.open("a", encoding="utf-8") as sink:
            for record in self.fetch_records(unseen_ids):
                sink.write(json.dumps(_record_to_json(record), ensure_ascii=True))
                sink.write("\n")
                seen_pmids.add(record.source_id)
                written += 1
        return written

    def _lookup_pmc_id(self, source_id: str) -> str | None:
        entrez = self._get_entrez()
        with entrez.elink(
            dbfrom="pubmed",
            db="pmc",
            id=source_id,
            linkname="pubmed_pmc",
        ) as handle:
            payload = entrez.read(handle)

        for link_set in payload:
            for link_set_db in link_set.get("LinkSetDb", []):
                for link in link_set_db.get("Link", []):
                    pmc_id = link.get("Id")
                    if pmc_id:
                        return str(pmc_id)
        return None

    def _parse_pubmed_article(self, article: ET.Element) -> RawRecord | None:
        citation = article.find("./MedlineCitation")
        article_node = citation.find("./Article") if citation is not None else None
        if citation is None or article_node is None:
            return None

        pmid = _first_text(citation, "./PMID")
        title = _normalize_text(_stringify_node(article_node.find("./ArticleTitle")))
        if not pmid or not title:
            return None

        abstract = _parse_abstract(article_node)
        authors, affiliations = _parse_authors(article_node)
        journal = _first_text(article_node, "./Journal/Title")
        publication_date = _parse_pub_date(article_node)
        doi = _extract_doi(article)
        keywords = _extract_keywords(citation)
        publication_types = _parse_publication_types(article_node)

        return RawRecord(
            source=self.source_name,
            source_id=pmid,
            title=title,
            abstract=abstract,
            authors=tuple(authors),
            journal=journal,
            publication_date=publication_date,
            doi=doi,
            affiliations=tuple(dict.fromkeys(affiliations)),
            keywords=tuple(keywords),
            publication_types=tuple(publication_types),
            raw=_element_to_dict(article),
        )

    def _configure_entrez(self, entrez: Any) -> None:
        entrez.email = self._email
        entrez.tool = self._tool
        if self._api_key:
            entrez.api_key = self._api_key

    def _get_entrez(self) -> Any:
        if EntrezModule is None:
            raise ModuleNotFoundError(
                "biopython is required for PubMedConnector. Install it with `uv add biopython`."
            )
        self._configure_entrez(EntrezModule)
        return EntrezModule

    def _fetch_pubmed_articles(self, ids: Sequence[str]) -> list[ET.Element]:
        root = self._fetch_xml(db="pubmed", ids=ids)
        return root.findall("./PubmedArticle")

    def _fetch_xml(self, *, db: str, ids: Sequence[str]) -> ET.Element:
        entrez = self._get_entrez()
        with entrez.efetch(
            db=db,
            id=",".join(ids),
            rettype="xml",
            retmode="xml",
        ) as handle:
            return ET.parse(handle).getroot()


def _batched(items: Sequence[str], size: int) -> Iterator[list[str]]:
    iterator = iter(items)
    while batch := list(islice(iterator, size)):
        yield batch


def _load_seen_pmids(output_file: Path) -> set[str]:
    if not output_file.exists():
        return set()

    seen: set[str] = set()
    with output_file.open("r", encoding="utf-8") as source:
        for line in source:
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            pmid = record.get("pmid") or record.get("source_id")
            if pmid:
                seen.add(str(pmid))
    return seen


def _record_to_json(record: RawRecord) -> dict[str, Any]:
    payload = asdict(record)
    publication_date = payload.get("publication_date")
    if isinstance(publication_date, date):
        payload["publication_date"] = publication_date.isoformat()
    payload["pmid"] = record.source_id
    return payload


def _parse_abstract(article_node: ET.Element) -> str | None:
    sections: list[str] = []
    for abstract_node in article_node.findall("./Abstract/AbstractText"):
        label = abstract_node.attrib.get("Label")
        text = _normalize_text(_stringify_node(abstract_node))
        if not text:
            continue
        sections.append(f"{label}: {text}" if label else text)
    return "\n\n".join(sections) or None


def _parse_authors(article_node: ET.Element) -> tuple[list[str], list[str]]:
    authors: list[str] = []
    affiliations: list[str] = []

    for author_node in article_node.findall("./AuthorList/Author"):
        author_name = _build_author_name(author_node)
        if author_name:
            authors.append(author_name)

        for affiliation_node in author_node.findall("./AffiliationInfo/Affiliation"):
            affiliation = _normalize_text(_stringify_node(affiliation_node))
            if affiliation:
                affiliations.append(affiliation)

    deduped_affiliations = list(dict.fromkeys(affiliations))
    return authors, deduped_affiliations


def _parse_publication_types(article_node: ET.Element) -> list[str]:
    publication_types: list[str] = []
    for type_node in article_node.findall("./PublicationTypeList/PublicationType"):
        publication_type = _normalize_text(_stringify_node(type_node))
        if publication_type:
            publication_types.append(publication_type)
    return publication_types


def _first_text(node: ET.Element, path: str) -> str | None:
    target = node.find(path)
    if target is None or target.text is None:
        return None
    value = target.text.strip()
    return value or None


def _stringify_node(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext())


def _normalize_text(value: str) -> str | None:
    cleaned = " ".join(value.split())
    return cleaned or None


def _build_author_name(author: ET.Element) -> str | None:
    collective = _first_text(author, "./CollectiveName")
    if collective:
        return collective

    last_name = _first_text(author, "./LastName")
    fore_name = _first_text(author, "./ForeName")
    if last_name and fore_name:
        return f"{fore_name} {last_name}"
    return last_name or fore_name


def _parse_pub_date(article_node: ET.Element) -> date | None:
    pub_date = article_node.find("./Journal/JournalIssue/PubDate")
    if pub_date is None:
        return None

    year_text = _first_text(pub_date, "./Year")
    medline_date = _first_text(pub_date, "./MedlineDate")
    if year_text is None and medline_date:
        digits = "".join(char for char in medline_date if char.isdigit())
        year_text = digits[:4] or None
    if year_text is None:
        return None

    try:
        year = int(year_text)
    except ValueError:
        return None

    month = _parse_month(_first_text(pub_date, "./Month")) or 1
    day = _parse_day(_first_text(pub_date, "./Day")) or 1

    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, 1)


def _parse_month(month_text: str | None) -> int | None:
    if not month_text:
        return None

    month_lookup = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    if month_text.isdigit():
        value = int(month_text)
        return value if 1 <= value <= 12 else None
    return month_lookup.get(month_text[:3].lower())


def _parse_day(day_text: str | None) -> int | None:
    if not day_text or not day_text.isdigit():
        return None
    value = int(day_text)
    return value if 1 <= value <= 31 else None


def _extract_doi(article: ET.Element) -> str | None:
    article_node = article.find("./MedlineCitation/Article")
    if article_node is None:
        return None

    for id_node in article_node.findall("./ELocationID"):
        if id_node.attrib.get("EIdType", "").lower() == "doi":
            doi = _normalize_text(_stringify_node(id_node))
            if doi:
                return doi

    pubmed_data = article.find("./PubmedData")
    if pubmed_data is None:
        return None
    for article_id in pubmed_data.findall("./ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType", "").lower() == "doi":
            doi = _normalize_text(_stringify_node(article_id))
            if doi:
                return doi
    return None


def _extract_keywords(citation: ET.Element) -> list[str]:
    keywords: list[str] = []
    for keyword in citation.findall("./KeywordList/Keyword"):
        text = _normalize_text(_stringify_node(keyword))
        if text:
            keywords.append(text)
    for mesh_heading in citation.findall("./MeshHeadingList/MeshHeading"):
        descriptor = _normalize_text(_stringify_node(mesh_heading.find("./DescriptorName")))
        if descriptor:
            keywords.append(descriptor)
    return list(dict.fromkeys(keywords))


def _element_to_dict(node: ET.Element) -> dict[str, Any]:
    children = list(node)
    payload: dict[str, Any] = {
        "tag": node.tag,
        "attributes": dict(node.attrib),
    }

    text = _normalize_text(node.text or "")
    if text:
        payload["text"] = text

    if not children:
        return payload

    grouped: dict[str, list[Any]] = {}
    for child in children:
        grouped.setdefault(child.tag, []).append(_element_to_dict(child))

    payload["children"] = {
        tag: items[0] if len(items) == 1 else items
        for tag, items in grouped.items()
    }
    return payload
