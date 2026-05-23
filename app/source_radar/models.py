from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class SourceItem:
    source_type: str
    title: str
    url: str
    snippet: str
    adapter: str = "fixture"
    retrieved_at: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceCard:
    id: str
    source_type: str
    title: str
    url: str
    summary: str
    adapter: str = "fixture"
    retrieved_at: str = ""
    content_hash: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


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


@dataclass(frozen=True)
class ProbeResult:
    adapter: str
    status: str
    reason: str
    message: str
    checked_at: str
    source_type: str = ""
    items_found: int = 0
    details: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HealthReport:
    status: str
    checked_at: str
    summary: dict[str, str]
    probes: list[ProbeResult]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IntegrationRecord:
    name: str
    source: str
    license: str
    core_policy: str
    status: str
    boundary: str
    notice: str


@dataclass(frozen=True)
class IntegrationAudit:
    status: str
    summary: dict[str, str]
    items: list[IntegrationRecord]

    def to_dict(self) -> dict:
        return asdict(self)
