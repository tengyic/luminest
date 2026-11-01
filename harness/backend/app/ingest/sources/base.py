"""Shared vocabulary for ingestion sources.

A source fetches *raw* concept records. It does not classify, does not assign
difficulty and does not invent prerequisites - that is the job of
``app.ingest.classify``. Keeping the split means a new source only has to answer
"what concepts exist and how does this source order them".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Protocol, runtime_checkable

from ..policy import SourcePolicy


class SourceError(RuntimeError):
    """A source could not produce data (network, cache miss, malformed file)."""


@dataclass
class RawNode:
    """One concept as reported by a source, before classification."""

    title: str
    #: Position within the source's own ordering. Lower comes first.
    order: int = 0
    strand_hint: str = ''
    unit_hint: str = ''
    topic_hint: str = ''
    summary: str = ''
    keywords: list[str] = field(default_factory=list)
    #: Titles (or ids) this concept depends on, exactly as the source declares them.
    prerequisites: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    #: True when the source itself asserts the ordering as a teaching sequence.
    ordered: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'RawNode':
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


@runtime_checkable
class Source(Protocol):
    """Anything that can produce raw concept records."""

    name: str

    def policy(self) -> SourcePolicy:
        ...

    def fetch(self) -> list[RawNode]:
        ...


class StaticSource:
    """A source backed by an in-memory list. Used for bundled corpora and tests."""

    def __init__(self, name: str, policy: SourcePolicy, nodes: Iterable[RawNode]):
        self.name = name
        self._policy = policy
        self._nodes = list(nodes)

    def policy(self) -> SourcePolicy:
        return self._policy

    def fetch(self) -> list[RawNode]:
        return [RawNode.from_dict(n.to_dict()) for n in self._nodes]
