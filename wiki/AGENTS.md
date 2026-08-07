# Platform operating instructions

All agents on this platform follow these rules. Domain and case AGENTS.md
files extend them - they never repeat them.

## Behaviour
- Cite a source for every factual claim: a source note, a chunk ID from the
  query index, or an entity ID from the knowledge graph. No source, no claim.
- Mark inference explicitly. Facts read from documents are stated plainly;
  conclusions you derived are prefixed "Assessment:".
- When evidence conflicts, record both positions. Never silently resolve a
  conflict - flag it in open-questions.md and move on.
- Escalate to a human when: authority thresholds are exceeded, evidence
  conflicts block a conclusion, or confidence in a material claim is low.

## Vocabulary
- Peril and coverage labels come from wiki/vocabulary/ only. If no term
  fits, propose one in lessons.md - do not invent free text inline.

## Writing to the wiki
- Writes go through propose_wiki_kb_update(). Direct file writes are for
  humans only.
- decisions.md is append-only. Never edit an existing decision record.
