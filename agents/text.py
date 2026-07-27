"""House style for text on its way into the wiki.

The platform rules say plain ASCII punctuation: no em dashes, " - " as the
separator, "->" for arrows. A model does not always agree. Left alone, its
output arrives in the wiki carrying non-breaking hyphens and en dashes that
look identical on screen, break a grep for an identifier, and land in the next
rebuild as chunk text nobody can search for.

So normalisation happens once, at the boundary where composed text becomes a
wiki write, and it reports what it changed. A silent cleanup nobody can see is
a cleanup nobody can audit - the count goes on the trace line.

Characters are written as escapes here on purpose: a non-breaking hyphen and a
hyphen are the same glyph on screen, and a rule nobody can read is a rule
nobody can check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Dashes that read as a separator between words. They become " - ", the
# separator the house style uses.
SEPARATORS = (
    "\u2013"  # en dash
    "\u2014"  # em dash
    "\u2015"  # horizontal bar
)

# Dashes that read as a hyphen inside or between words.
HYPHENS = {
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2012": "-",  # figure dash
    "\u2212": "-",  # minus sign
}

# Invisible characters that survive a copy out of a model answer and leave an
# identifier failing to match itself.
INVISIBLES = {
    "\u00ad": "",  # soft hyphen
    "\u200b": "",  # zero width space
    "\ufeff": "",  # zero width no-break space
}

# Spaces around a separator dash are collapsed with it, but a line break is
# not: paragraphs stay where the drafter put them.
_SEPARATOR = re.compile(rf"[ \t]*[{SEPARATORS}][ \t]*")

_TRANSLATION = str.maketrans(HYPHENS | INVISIBLES)


@dataclass(frozen=True)
class Normalised:
    """Text in house style, and what it took to get there."""

    text: str
    replacements: int

    @property
    def changed(self) -> bool:
        return self.replacements > 0


def normalise(text: str) -> Normalised:
    """Rewrite exotic dashes as ASCII and count every character replaced."""
    replacements = sum(text.count(character) for character in (*SEPARATORS, *HYPHENS, *INVISIBLES))
    return Normalised(
        text=_SEPARATOR.sub(" - ", text).translate(_TRANSLATION), replacements=replacements
    )
