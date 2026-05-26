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
    confidence: str = "unknown"
    confidence_reason: str = ""


@dataclass(frozen=True)
class InformationAnalysis:
    summary: str
    key_points: list[str]
    source_notes: list[str]
    disagreements: list[str]
    noise_notes: list[str]


@dataclass(frozen=True)
class VerifyReport:
    claim: str
    status: str
    evidence: list[EvidenceCard]
    judgement: Judgement
    agent: "AgentTrace | None" = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SynthesisReport:
    query: str
    status: str
    evidence: list[EvidenceCard]
    analysis: InformationAnalysis
    agent: "AgentTrace | None" = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentTrace:
    mode: str
    ai_status: str
    model: str
    planned_tools: list[str]
    tool_calls: list[dict[str, str]]
    acquisition: list["AcquisitionTrace"] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateSource:
    title: str
    url: str
    provider: str
    snippet: str = ""
    source_type: str = "web-page"
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AcquisitionTrace:
    provider: str
    provider_type: str
    status: str
    reason: str
    message: str
    candidate_count: int = 0
    items_found: int = 0
    candidates: list[CandidateSource] = field(default_factory=list)
    fix: str = ""
    retryable: bool = False
    warnings: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)


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
