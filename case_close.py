"""Closing a case: what it leaves behind for the next one.

This is the compounding step, and it is deliberately not an agent step. An
agent drafts, a human decides, and promoting a case lesson into the platform
layer is a decision - it changes what every future case in the class retrieves.
So the ceremony is performed here, by the demo standing in for the human and
the Main Orchestrator together, and it still goes through propose_wiki_update:
the same door, the same guardrails, the same trace line. Agents never touch
storage, and neither does anything else in this repo.

Two files are written, in the shape the wiki already uses:

  the case lessons.md            what this case learned, marked promoted
  platform-ic/engagement-lessons what the platform now knows, for every case
                                 in the class

After the indexes are rebuilt, the precedent query that ran in beat two returns
one more result than it did - the new lesson hangs off the risk class, so the
next submission in this class finds it without anyone being told to look.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.specialists import DEPTH, PRECEDENT_QUERY, TOP_K
from errors import WriteRefused
from ingest import entities
from mcp_server import tools, writes
from mcp_server.context import ToolContext
from mcp_server.results import WriteResult

LESSONS_FILE = "lessons.md"
PLATFORM_DIR = "wiki/platform-ic/engagement-lessons"


@dataclass(frozen=True)
class Lesson:
    """The lesson a closing case promotes, and where it lands."""

    lesson_id: str
    title: str
    slug: str
    case_body: str
    platform_body: str

    def platform_path(self) -> str:
        return f"{PLATFORM_DIR}/{self.slug}.md"

    def vault_path(self) -> str:
        return self.platform_path().removeprefix("wiki/")


@dataclass(frozen=True)
class Promotion:
    """What the ceremony wrote, for the caller and for the screen."""

    case_id: str
    lesson: Lesson
    written: tuple[WriteResult, ...]


@dataclass(frozen=True)
class Page:
    """A file to write: what it opens with, and the section that carries it.

    The two are kept apart because they are written by two different operations
    - the whole page when the file is new, the section alone when the ceremony
    is run a second time over a wiki nobody reset.
    """

    opening: str
    section: str

    @property
    def text(self) -> str:
        return f"{self.opening}\n{self.section}"


@dataclass(frozen=True)
class Precedent:
    """One run of the precedent query: what search found, what the graph held."""

    chunk_ids: tuple[str, ...]
    scores: tuple[float, ...]
    entity_ids: tuple[str, ...]

    @property
    def results(self) -> int:
        """Every result the query returned, chunks and entities alike."""
        return len(self.chunk_ids) + len(self.entity_ids)


# The lesson SUB-2025-007 closes on. Two cases in this class have now turned on
# a system the insured does not operate, which is what turns a case observation
# into a platform rule.
VENDOR_ACCESS = Lesson(
    lesson_id="L-002",
    title="Vendor standing access is a submission question, not a pricing note",
    slug="vendor-access-cyber-logistics",
    case_body=(
        "Baltra runs its warehouse management system on a provider it does not "
        "control, the same shape as [[submissions/SUB-2024-018/index|SUB-2024-018]], "
        "where the loss entered through the vendor's remote access channel and "
        "coverage turned on CY-EX-04. The lesson recorded on that claim - see "
        "[[claims/CLM-2024-042/lessons|CLM-2024-042 lessons]], L-001 - was a "
        "candidate for platform promotion. A second case in the same class "
        "settles it: vendor standing access is asked about at submission, "
        "before the appetite position, not reconstructed after a loss."
    ),
    platform_body=(
        "Two cyber-logistics cases have now turned on a system the insured does "
        "not operate. Treat vendor standing access as an exposure path in its "
        "own right, not a pricing note on the schedule.\n\n"
        "When to apply: any cyber-logistics submission where a core operating "
        "system is run by a third party.\n\n"
        "1. Ask who operates the system, what standing access they hold, and "
        "whose controls are scheduled against it.\n"
        "2. Price the concentration: one system across every site is one loss "
        "across every site.\n"
        "3. Say explicitly how the wording allocates vendor risk. CY-EX-04 left "
        "ambiguous is the argument you have at claim time.\n\n"
        "Evidence: [[claims/CLM-2024-042/lessons|CLM-2024-042 lessons]] (L-001), "
        "[[submissions/SUB-2024-018/index|SUB-2024-018]], "
        "[[submissions/SUB-2025-007/index|SUB-2025-007]]."
    ),
)


def close_case(
    context: ToolContext,
    case_id: str,
    case_dir: str,
    risk_class: str,
    stamp: str,
    lesson: Lesson = VENDOR_ACCESS,
) -> Promotion:
    """Record the case lesson and promote it to the platform layer."""
    written = (
        _write(context, f"{case_dir}/{LESSONS_FILE}", case_lesson(case_id, lesson, stamp)),
        _write(
            context, lesson.platform_path(), platform_lesson(case_id, risk_class, lesson, stamp)
        ),
    )
    return Promotion(case_id=case_id, lesson=lesson, written=written)


def precedent_query(context: ToolContext, risk_class: str) -> Precedent:
    """The beat two precedent query, run again, argument for argument.

    The strings come from agents/specialists.py rather than a copy of them, so
    what beat five re-runs is what beat two ran and the comparison means
    something.
    """
    hits = tools.search_knowledge_base(
        context, PRECEDENT_QUERY.format(risk_class=risk_class), top_k=TOP_K
    )
    subgraph = tools.traverse_graph(
        context,
        entities.node_id(entities.RISK_CLASS, risk_class),
        [entities.IN_CLASS, entities.HAS_LESSON],
        depth=DEPTH,
    )
    return Precedent(
        chunk_ids=tuple(hit["chunk_id"] for hit in hits),
        scores=tuple(hit["score"] for hit in hits),
        entity_ids=tuple(node["id"] for node in subgraph["nodes"]),
    )


def case_lesson(case_id: str, lesson: Lesson, stamp: str) -> Page:
    """The lessons.md a closing case leaves in its own directory."""
    return Page(
        opening=(
            f"---\n"
            f"case_id: {case_id}\n"
            f"status: promoted\n"
            f"promoted_to: {lesson.vault_path()}\n"
            f"closed: {stamp}\n"
            f"---\n\n"
            f"# Lessons\n"
        ),
        section=f"## {lesson.lesson_id} - {lesson.title}\n{lesson.case_body}\n",
    )


def platform_lesson(case_id: str, risk_class: str, lesson: Lesson, stamp: str) -> Page:
    """The platform-ic file every future case in the class retrieves.

    The date sits in the frontmatter and never in the body: the body is what
    gets chunked and embedded, and a rebuild should produce the same chunks
    today as it did the day the case closed.
    """
    return Page(
        opening=(
            f"---\n"
            f"lesson_id: {lesson.lesson_id}\n"
            f"domain: {risk_class}\n"
            f"promoted: {stamp}\n"
            f"source_cases: [SUB-2024-018, CLM-2024-042, {case_id}]\n"
            f"---\n\n"
            f"# Vendor standing access in {risk_class}\n"
        ),
        section=f"## {lesson.lesson_id} - {lesson.title}\n{lesson.platform_body}\n",
    )


def _write(context: ToolContext, path: str, page: Page) -> WriteResult:
    """Create the file, or replace the section if the ceremony already ran.

    A rehearsal nobody reset should not fail at the last beat. The second write
    says exactly what the first one said, and replacing the section it owns is
    a smaller claim than rewriting the file around it.
    """
    try:
        return tools.propose_wiki_update(context, path, writes.CREATE_FILE, page.text)
    except WriteRefused:
        return tools.propose_wiki_update(context, path, writes.REPLACE_SECTION, page.section)
