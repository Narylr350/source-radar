from .models import SourceItem


FIXTURE_ITEMS = [
    SourceItem(
        source_type="project-doc",
        title="source-radar project README",
        url="local://README.md",
        snippet=(
            "source-radar is a local, AI-friendly CLI and collection "
            "engine for Chinese internet source verification."
        ),
    )
]


def collect_fixture_items(claim: str) -> list[SourceItem]:
    normalized = claim.lower()
    if "source-radar" in normalized or "本地 cli" in normalized:
        return FIXTURE_ITEMS
    return []
