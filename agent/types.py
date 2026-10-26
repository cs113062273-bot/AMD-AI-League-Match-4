from __future__ import annotations

import os
import time
import math
from dataclasses import dataclass, field, asdict


def read_budget():
    try:
        value=float(os.getenv("APERTURE_BUDGET", "24"))
        return min(26.0,max(0.1,value)) if math.isfinite(value) else 24.0
    except ValueError:
        return 24.0


@dataclass
class Settings:
    budget: float = 24.0
    request_timeout: float = 5.0
    max_pages: int = 10
    max_depth: int = 2
    concurrency: int = 5
    max_bytes: int = 1_500_000
    allow_private: bool = False
    search: bool = True
    model_url: str = "http://127.0.0.1:8765"
    model_timeout: float = 5.0
    browser: bool = False
    search_providers: list | None = None

    @classmethod
    def from_env(cls):
        return cls(budget=read_budget(),
                   allow_private=os.getenv("APERTURE_ALLOW_PRIVATE") == "1",
                   search=os.getenv("APERTURE_SEARCH", "1") == "1",
                   model_url=os.getenv("APERTURE_MODEL_URL", "http://127.0.0.1:8765"),
                   browser=os.getenv("APERTURE_BROWSER") == "1")


@dataclass
class Deadline:
    seconds: float
    start: float = field(default_factory=time.monotonic)
    # One Engine.run owns one deadline. Never retain refusals across queries.
    _model_capacity_rejections: set = field(default_factory=set, init=False, repr=False, compare=False)
    model_capacity_skips: int = field(default=0, init=False, repr=False, compare=False)

    @property
    def remaining(self):
        return max(0.0, self.seconds - (time.monotonic() - self.start))

    def timeout(self, cap=5.0, reserve=0.3):
        return max(0.001, min(cap, self.remaining - reserve))


@dataclass
class Plan:
    question: str
    url: str = ""
    kind: str = "text"
    terms: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    entity_terms: list[str] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    year: str = ""
    as_of: str = ""
    latest: bool = False
    stable: bool = False
    first: bool = False
    currency: str = ""
    cardinality: int = 1
    negations: list[str] = field(default_factory=list)
    domain: str = ""
    focus: str = ""
    choices: list[str] = field(default_factory=list)
    operation: str = 'single'
    required_fields: list[str] = field(default_factory=list)
    date_precision: str = ''
    temporal_issue: str = ''
    temporal_raw: list[str] = field(default_factory=list)


@dataclass
class Passage:
    text: str
    label: str = ""
    value: str = ""
    section: str = ""
    kind: str = "prose"
    locator: str = ""
    qualifiers: dict = field(default_factory=dict)


@dataclass
class Page:
    url: str
    title: str = ""
    passages: list[Passage] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)
    canonical: str = ""
    redirects: list[str] = field(default_factory=list)
    status: int = 200
    error: str = ""
    truncated: bool = False
    dynamic: bool = False
    identity: dict = field(default_factory=dict)


@dataclass
class Candidate:
    raw: str
    answer: str
    source: str
    evidence: str
    label: str = ""
    section: str = ""
    kind: str = "text"
    score: float = 0
    signals: dict = field(default_factory=dict)


@dataclass
class Result:
    answer: str = ""
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0
    evidence: str = ""
    reason: str = "no_evidence"
    diagnostics: dict = field(default_factory=dict)

    def internal(self):
        return asdict(self)
