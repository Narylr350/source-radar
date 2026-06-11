from dataclasses import asdict, dataclass, field

_SCORE_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class QualityAssessment:
    score: str
    signals: list[str]
    reason: str
    suggestions: list[str]

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, QualityAssessment):
            return NotImplemented
        return _SCORE_ORDER.get(self.score, -1) < _SCORE_ORDER.get(other.score, -1)


@dataclass(frozen=True)
class SourceItem:
    source_type: str
    title: str
    url: str
    snippet: str
    adapter: str = "fixture"
    retrieved_at: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    raw_content: str = ""
    raw_content_length: int = 0
    raw_content_truncated: bool = False


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
    raw_excerpt: str = ""
    raw_content_length: int = 0
    raw_content_truncated: bool = False
    distilled: dict = field(default_factory=dict)
    compression: dict = field(default_factory=dict)


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
class ResearchRound:
    round: int
    queries: list[dict]
    evidence_before_dedupe: int
    evidence_after_dedupe: int
    evaluator: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchReport:
    query: str
    status: str
    requested_max_rounds: int
    executed_rounds: int = 0
    multi_round_enabled: bool = False
    plan: dict = field(default_factory=dict)
    queries: list[dict] = field(default_factory=list)
    rounds: list[ResearchRound] = field(default_factory=list)
    evidence_count_before_dedupe: int = 0
    evidence_count: int = 0
    source_profile: dict[str, int] = field(default_factory=dict)
    consensus: str = "unclear"
    transferability: str = "unclear"
    applicability: str = "not_enough"
    risk_level: str = "unknown"
    gaps: list[str] = field(default_factory=list)
    conclusion: str = ""
    recommended_steps: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    evidence: list[EvidenceCard] = field(default_factory=list)
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
    # v3 hardening trace fields
    context_used: bool = False
    session_id: str = ""
    context_records_read: int = 0
    context_ignore_reason: str = ""
    reused_evidence_count: int = 0
    fresh_evidence_count: int = 0
    actually_used_tools: list[str] = field(default_factory=list)
    skipped_tools: list[dict] = field(default_factory=list)
    cache_hit_count: int = 0
    fresh_tool_count: int = 0
    evidence_input_profile: dict = field(default_factory=dict)


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
    quality: QualityAssessment | None = None


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
