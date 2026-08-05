"""The projector surface: what the room sees while the demo runs.

Everything here is presentation and nothing here is behaviour. The run decides
what happened; this decides how it reads from the back of a room - one panel
per phase, wide type, no colour that dies on a beamer, and the tool calls
echoed in monospace exactly as they were made, each behind the agent that made
it. The strings in the deck and the strings on screen have to be the same
strings, so the echo formats the arguments the trace recorded rather than a
tidied-up version of them.

The pause is the other half of the job. A demo that runs to the end on its own
is a video; the presenter stops between phases, takes the question, and moves
on when they are ready.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Mapping, Sequence

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

PANEL = "bold white on dark_blue"
CALL = "bold cyan"
RESULT = "green"
HUMAN = "bold yellow"
NOTE = "italic bright_black"
WARN = "bold yellow"
NEW = "bold green"


class Stage:
    """One console, one house style, one keypress between beats."""

    def __init__(self, console: Console | None = None, paused: bool = True) -> None:
        self.console = console or Console(highlight=False, soft_wrap=False)
        self.paused = paused

    def title(self, heading: str, subtitle: str) -> None:
        self.console.print()
        self.console.print(Panel(Text(heading, style="bold"), subtitle=subtitle, expand=True))

    def beat(self, heading: str, claim: str) -> None:
        """Open a panel with what it is about to demonstrate.

        The heading is written out by the caller rather than assembled here:
        the phases of the run are named after what they do and where they sit
        in the swarm flow, and no two of them are named the same way.
        """
        self.console.print()
        self.console.print(
            Panel(
                Text(claim),
                title=Text(f" {heading} ", style=PANEL),
                title_align="left",
                expand=True,
            )
        )

    def pause(self, prompt: str = "continue") -> None:
        """Wait for the presenter. --no-pause runs the whole thing unattended."""
        if not self.paused:
            return
        self.console.print()
        self.console.input(Text(f"  [enter] {prompt} ", style=NOTE))

    def step(self, text: str) -> None:
        self.console.print(Text(f"  {text}", style="bold"))

    def note(self, text: str) -> None:
        self.console.print(Text(f"  {text}", style=NOTE))

    def warn(self, text: str) -> None:
        self.console.print(Text(f"  ! {text}", style=WARN))

    def human(self, text: str) -> None:
        self.console.print(Text(f"  human: {text}", style=HUMAN))

    def call(self, tool: str, args: Mapping[str, object], agent: str = "") -> None:
        """Echo one tool call exactly as it was made, behind whoever made it."""
        caller = f"{agent} " if agent else ""
        self.console.print(Text(f"  {caller}-> {signature(tool, args)}", style=CALL))

    def returned(self, text: str) -> None:
        self.console.print(Text(f"     {text}", style=RESULT))

    def refused(self, text: str) -> None:
        self.console.print(Text(f"     refused: {text}", style=WARN))

    def table(self, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        table = Table(box=None, pad_edge=False, show_edge=False)
        for index, column in enumerate(columns):
            table.add_column(column, justify="right" if index and column[0].isupper() else "left")
        for row in rows:
            table.add_row(*row)
        self.console.print(table)

    def markdown(self, text: str, title: str) -> None:
        self.console.print(Panel(Markdown(text), title=title, title_align="left", expand=True))

    def diff(self, before: str, after: str, path: str) -> None:
        """A unified diff of one file, added lines in green."""
        lines = list(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=path,
                tofile=path,
                lineterm="",
                n=1,
            )
        )
        if not lines:
            self.note(f"{path} unchanged")
            return
        body = Text()
        for line in lines:
            style = "green" if line.startswith("+") else "red" if line.startswith("-") else NOTE
            body.append(line + "\n", style=style)
        self.console.print(Panel(body, title=f"diff - {path}", title_align="left", expand=True))

    def compare(self, label: str, before: object, after: object, gained: Sequence[str]) -> None:
        """A count before and after, with whatever is new named."""
        arrow = Text(f"  {label}: ", style="bold")
        arrow.append(f"{before} -> {after}", style=NEW if gained else "bold")
        self.console.print(arrow)
        for value in gained:
            self.console.print(Text(f"     new: {value}", style=NEW))


def signature(tool: str, args: Mapping[str, object]) -> str:
    """A call as it would be written in code, from the arguments it was given."""
    rendered = ", ".join(f"{name}={value_of(value)}" for name, value in args.items())
    return f"{tool}({rendered})"


def value_of(value: object) -> str:
    """One argument, in Python's spelling rather than JSON's."""
    if value is None or isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(value_of(item) for item in value) + "]"
    return str(value)
