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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agents.context import cited_ids
from agents.validate import BOTH_POSITIONS
from mcp_server.context import ToolContext


def count_words(text: str) -> int:
    """Stand-in token counter: offline, deterministic, obviously not exact."""
    return len(text.split())


@dataclass(frozen=True)
class Sandbox:
    """The demo wiki, copied and indexed, with everything an agent may cite."""

    context: ToolContext
    ids: frozenset[str]  # every chunk id and entity id the index held when it was built
    rebuild: Callable[[], None]  # regenerate both indexes from the sandbox markdown

    def written(self, case_dir: str, name: str) -> str:
        """Read back a case file the run wrote to."""
        return (self.path(case_dir, name)).read_text(encoding="utf-8")

    def path(self, case_dir: str, name: str) -> Path:
        return self.context.wiki_dir.parent / case_dir / name

    def exists(self, path: str) -> bool:
        """True when a wiki path - wiki/platform-ic/... - is a file in the sandbox."""
        return (self.context.wiki_dir.parent / path).is_file()


class FakeLLM:
    """A deterministic model, grounded in the prompt it was handed.

    It cites ids it finds in the prompt and one it makes up. The invented id is
    the point: a run over this fake exercises the citation strip rather than
    assuming it works. invents=False turns that off, for the tests that need a
    run where every claim is supported and cross-validation comes back clean.
    """

    INVENTED = "Case:INVENTED-000"
    # A non-breaking hyphen and an em dash, the two the drafter is asked not to
    # produce, so a run over this fake exercises the normalisation as well.
    EXOTIC = "vendor\u2011operated systems \u2014 the loss path"
    # What the drafter opens with when the findings it was handed disagree.
    ALERT = "### Coverage Conflict Alert: "

    def __init__(
        self, severity: str = "high", position: str = "in-appetite", invents: bool = True
    ) -> None:
        self.grades = {"severity": severity, "position": position}
        self.invents = invents
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        found = [value for value in cited_ids(prompt) if value != self.INVENTED]
        if "drafting agent" in system:
            return self.draft(found, prompt)
        return self.assessment(found, prompt)

    def draft(self, found: list[str], prompt: str) -> str:
        """The composed draft, opened with an alert when the findings conflict.

        The heading is written from the conflict the prompt actually carries,
        never from a constant: what is under test is that the composer produces
        it off the findings, and a fake that emitted one regardless would prove
        the opposite.
        """
        supported = f" [{found[0]}]" if found else ""
        opening = f"Assessment: {self.EXOTIC} matches the pattern already on file{supported}."
        body = opening
        if self.invents:
            body = f"{opening}\n\nAssessment: one point needs a human [{self.INVENTED}]."
        conflict = self.conflict(prompt)
        return f"{self.ALERT}{conflict}\n\n{body}" if conflict else body

    @staticmethod
    def conflict(prompt: str) -> str:
        """What the findings say is in dispute, or "" when they hold together."""
        for line in prompt.splitlines():
            if BOTH_POSITIONS in line:
                return line.split(" - ", 1)[0].removeprefix("- ").strip()
        return ""

    def assessment(self, found: list[str], prompt: str) -> str:
        findings: list[dict[str, object]] = [
            {"claim": "Evidenced claim.", "citations": [*found[:2], self.INVENTED]}
        ]
        if self.invents:
            findings.append(
                {
                    "claim": f"Unsupported claim about {self.INVENTED}.",
                    "citations": [self.INVENTED],
                }
            )
        payload: dict[str, object] = {"findings": findings}
        for label, value in self.grades.items():
            if f'"{label}"' in prompt:
                payload[label] = value
        return json.dumps(payload)
