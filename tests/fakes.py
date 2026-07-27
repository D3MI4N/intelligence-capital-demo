"""The stand-ins the agent tests share: a token counter, a model, a sandbox wiki.

The model is the important one. An agent test that called the provider would
be slow, expensive and different every run; one that returned a fixed string
would prove the plumbing and nothing else. FakeLLM answers in the contract the
specialists ask for, grounded in the ids it was actually given, plus one id it
invents - so every run exercises the rule that an agent may cite only what
retrieval returned.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agents.context import cited_ids
from mcp_server.context import ToolContext


def count_words(text: str) -> int:
    """Stand-in token counter: offline, deterministic, obviously not exact."""
    return len(text.split())


@dataclass(frozen=True)
class Sandbox:
    """The demo wiki, copied and indexed, with everything an agent may cite."""

    context: ToolContext
    ids: frozenset[str]  # every chunk id and entity id the index holds

    def written(self, case_dir: str, name: str) -> str:
        """Read back a case file the run wrote to."""
        return (self.path(case_dir, name)).read_text(encoding="utf-8")

    def path(self, case_dir: str, name: str) -> Path:
        return self.context.wiki_dir.parent / case_dir / name


class FakeLLM:
    """A deterministic model, grounded in the prompt it was handed.

    It cites ids it finds in the prompt and one it makes up. The invented id is
    the point: a run over this fake exercises the citation strip rather than
    assuming it works.
    """

    INVENTED = "Case:INVENTED-000"

    def __init__(self, severity: str = "high", position: str = "in-appetite") -> None:
        self.grades = {"severity": severity, "position": position}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        found = [value for value in cited_ids(prompt) if value != self.INVENTED]
        if "drafting agent" in system:
            return self.draft(found)
        return self.assessment(found, prompt)

    def draft(self, found: list[str]) -> str:
        supported = f" [{found[0]}]" if found else ""
        return (
            f"Assessment: the case matches the pattern already on file{supported}.\n\n"
            f"Assessment: one point needs a human [{self.INVENTED}]."
        )

    def assessment(self, found: list[str], prompt: str) -> str:
        payload: dict[str, object] = {
            "findings": [
                {"claim": "Evidenced claim.", "citations": [*found[:2], self.INVENTED]},
                {
                    "claim": f"Unsupported claim about {self.INVENTED}.",
                    "citations": [self.INVENTED],
                },
            ]
        }
        for label, value in self.grades.items():
            if f'"{label}"' in prompt:
                payload[label] = value
        return json.dumps(payload)
