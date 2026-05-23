from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SourceItem:
    source_type: str
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class EvidenceCard:
    id: str
    source_type: str
    title: str
    url: str
    summary: str


@dataclass(frozen=True)
class Judgement:
    status: str
    summary: str
    evidence_ids: list[str]
    gaps: list[str]


@dataclass(frozen=True)
class VerifyReport:
    claim: str
    status: str
    evidence: list[EvidenceCard]
    judgement: Judgement

    def to_dict(self) -> dict:
        return asdict(self)
