"""What the platform raises when it will not do what was asked.

One base class, so a caller can catch every refusal in one place, and one
subclass per reason, so a caller that cares about the difference has it. Every
message names the offending value and what would have been acceptable - an
agent reads the message and retries, it does not read a stack trace.

The module sits at the root rather than inside a package because refusals come
from two layers - the storage package and the tools over it - and neither
should have to import the other to raise one.
"""

from __future__ import annotations


class ToolError(Exception):
    """Base for every refusal an MCP tool raises."""


class IndexMissing(ToolError):
    """A derived index was queried before it was built."""


class UnknownCase(ToolError):
    """No case directory in the wiki carries the requested case id."""


class UnknownNode(ToolError):
    """The knowledge graph holds no node with the requested id."""


class InvalidRelation(ToolError):
    """A traversal asked for a relation the wiki vocabulary does not define."""


class InvalidDepth(ToolError):
    """A traversal asked for more hops than the tools will walk."""


class WriteRefused(ToolError):
    """A wiki write broke one of the write guardrails and did not happen."""
