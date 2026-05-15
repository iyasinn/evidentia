from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterator, Mapping, Optional, Sequence


@dataclass(slots=True)
class RawRecord:
    """Normalized record across all literature sources."""

    source: str
    source_id: str
    title: str
    abstract: Optional[str]
    authors: Sequence[str] = field(default_factory=tuple)
    journal: Optional[str] = None
    publication_date: Optional[date] = None
    doi: Optional[str] = None
    affiliations: Sequence[str] = field(default_factory=tuple)
    keywords: Sequence[str] = field(default_factory=tuple)
    publication_types: Sequence[str] = field(default_factory=tuple)
    raw: Mapping[str, Any] = field(default_factory=dict)


class LiteratureConnector(ABC):
    """Abstract interface for literature databases."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier, e.g. ``pubmed``."""

    @abstractmethod
    def search(self, query: str, max_results: int = 1000) -> list[str]:
        """Return source-specific IDs matching the query."""

    @abstractmethod
    def fetch_records(self, ids: Sequence[str]) -> Iterator[RawRecord]:
        """Yield normalized records for the given IDs."""

    def search_and_fetch(
        self,
        query: str,
        max_results: int = 1000,
    ) -> Iterator[RawRecord]:
        """Convenience helper that chains ``search`` and ``fetch_records``."""
        ids = self.search(query, max_results=max_results)
        yield from self.fetch_records(ids)

    def fetch_full_text(self, source_id: str) -> Optional[str]:
        """Return full text if accessible, else ``None``."""
        return None
