"""A miniature wiki on disk for the ingest tests.

Nothing here reaches the network. Tests that need vectors use the hash backend
from ingest/hash_embedder.py, the same one EMBED_BACKEND=hash selects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FILES: dict[str, str] = {
    "wiki/AGENTS.md": """# Platform rules

Agents follow these rules.

## Behaviour
Cite a source for every claim.

## Vocabulary
Terms come from wiki/vocabulary only.
""",
    "wiki/claims/CLM-9999-001/index.md": """---
case_id: CLM-9999-001
type: claim
status: settled-closed
class: cyber-logistics
insured: Testco Logistics BV
peril: [ransomware, vendor-compromise]
linked_submission: SUB-9999-001
opened: 2024-06-11
closed: 2024-11-28
---

# CLM-9999-001 - Testco - Ransomware

Coverage disputed on exclusion CY-EX-04, resolved for the insured.

## Related
- [[submissions/SUB-9999-001/index|SUB-9999-001]] - the originating submission
""",
    "wiki/claims/CLM-9999-001/lessons.md": """---
case_id: CLM-9999-001
status: candidate
---

# Lessons

## L-900 - Vendor standing access is a distinct exposure path
The claim entered through vendor infrastructure. See
[[submissions/SUB-9999-001/index|SUB-9999-001]] and skill SK-900.
""",
    "wiki/claims/CLM-9999-001/sources/note.md": """---
source_id: SRC-999-01
original: raw/testco-survey.md
ingested: 2024-06-11
---

# Source note - survey

Key facts:
- Single system across all sites

Locator: raw/testco-survey.md
""",
    "wiki/submissions/SUB-9999-001/index.md": """---
case_id: SUB-9999-001
type: submission
status: bound-closed
class: cyber-logistics
insured: Testco Logistics BV
peril_focus: [ransomware, network-outage]
linked_claim: CLM-9999-001
---

# SUB-9999-001 - Testco - Cyber

Bound with exclusions CY-EX-04 and CY-EX-01.
""",
    "wiki/platform-ic/skills/precedent.md": """---
skill_id: SK-900
domain: cyber-logistics
---

# Precedent search

Query the knowledge base before drafting an appetite position.
""",
    "wiki/submissions/SUB-9999-001/sources/.gitkeep": "",
    "wiki/notes.txt": "not markdown, must be skipped",
    "wiki/.obsidian/private.md": "# hidden vault config, must be skipped",
    "raw/testco-survey.md": """---
doc_id: RAW-900
type: risk-survey
claim: CLM-9999-001
insured: Testco Logistics BV
---

# Risk survey - Testco

One system serves every site.
""",
}


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[tuple[str, Path], ...]:
    """Write the fixture wiki and return roots in the shape parse_corpus wants."""
    for relative, content in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return (("wiki", tmp_path / "wiki"), ("raw", tmp_path / "raw"))
