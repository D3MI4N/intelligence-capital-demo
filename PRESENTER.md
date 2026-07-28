# Presenter's manual

How to run the Intelligence Capital demo in front of a room, from a machine
that has never seen it before. No API key is needed at any point: the demo
replays a blessed recording committed in this repo, so every run shows the
same assessment, the same numbers, and the same payoff.

Reading this file: 
- **On screen** is what the terminal shows. 
- **Do** is a physical action. 
- **Say** followed by bold text in quotes is what the
presenter speaks - everything bold is spoken, everything else is stage
direction.

## Before the day

On the presenting machine, once:

    git clone <repo-url>
    cd intelligence-capital-demo
    uv sync
    uv run python demo.py reset --replay

The reset restores the wiki, installs the recording, and rebuilds the
indexes. Expect it to end with: documents 33, chunks 35, graph nodes 46,
graph edges 78. If those counts appear, the machine is ready.

Screen setup: terminal left, Obsidian right, with wiki/ opened as a vault.
Any terminal works - a plain terminal app full-height with the font
enlarged is the cleanest stage; the VSCode integrated terminal is fine too
if the sidebar is hidden and the terminal panel maximized, so the room sees
the demo and not editor chrome. Rehearse at the projector's real
resolution: the panels wrap to terminal width.

In Obsidian: open the graph view once and check it renders; pin
`wiki/submissions/SUB-2025-007/briefing.md` in a tab.

Rehearse the full run at least once on this machine. It costs nothing and
takes ten minutes.

## Running order

    uv run python demo.py reset --replay
    uv run python demo.py run --replay

The run pauses between beats; enter advances. 

The rhythm of every beat is the same: let it render, speak, then press
enter - enter is always the last thing done in a beat, never the first.

Nothing else is typed during
the demo. If anything ever looks wrong, the recovery is always the same:
`ctrl+C`, then `reset --replay`, then `run --replay` from the top.

## The opening (before beat 1)

**Do:** Obsidian, graph view, ten seconds on screen.

**Say:** **"This is the knowledge base. Not a database behind an API - a
folder of markdown a person can read, edit and walk. Everything the agents
know is in these files; everything else is derived from them and rebuilt
with one command. Watch the terminal do exactly that."**

**Do:** switch to the terminal, start the run.

## Beat 1 - Orient

**On screen:** five file reads with a token count per file and a running
total, ending at 645 tokens.

**Say:** **"The orchestrator reads the rules before the case: platform
rules, domain rules, case rules, each layer extending the last. Watch the
right column - that is the entire bill for getting an agent situated, 645
tokens, before a single model call. And it stays bounded no matter how
large the knowledge base grows, because orientation reads the cascade, not
the corpus."**

**Do:** press enter - beat 2 renders.

## Beat 2 - Retrieve

**On screen:** four tool calls in monospace with real arguments, ranked
chunks with scores, entity subgraphs, then the specialists table. The call
order can differ between runs - the three specialists genuinely run in
parallel; membership and results are always the same.

**Say:** **"Three specialists, dispatched in parallel. Every call you see
is the real call, echoed from the audit trace. Search returns ranked
chunks, each carrying the id a claim will have to cite; the graph
traversal returns the entities and relations around the risk class. One
specialist uses both and merges them - that is GraphRAG, semantic and
structural retrieval combined."**

**Do:** point at the Cited column.

**Say:** **"Agents may only cite what retrieval actually gave them.
Anything else is stripped before it reaches a file."**

**Do:** point at the Context column.

**Say:** **"And the merged context per specialist is one to two thousand
tokens - bounded injection, not the whole wiki."**

**Do:** press enter - beat 3 renders.

## Beat 3 - Write back

**On screen:** two writes through `propose_wiki_update`, a normalisation
note, the composed draft, the briefing diff, and a dated record in
`decisions.md`.

**Say:** **"The draft goes back into the wiki through one door -
`propose_wiki_update` - with the guardrails in the door, not in the agent's
goodwill. Every claim carries its sources. And notice the third paragraph:
the graph holds no exclusion recorded against this risk class, yet the
precedent documents show exclusion CY-EX-04 applied at bind and disputed at
claim time. Two sources in the knowledge base disagree - and instead of
picking a side or papering over it, the agents flagged the conflict for a
human. The system reasons over what the knowledge base actually contains,
including its gaps."**

**Do:** point at the last line of the diff.

**Say:** **"Drafted, not decided. The record in `decisions.md` is dated, not
numbered - numbering is what a human does when they accept it."**

**Do:** switch to Obsidian, open `briefing.md`, click one citation link.

**Say:** **"The agent wrote a document, not a row in a database. A person
can read it, follow its sources, and edit it."**

**Do:** switch back to the terminal, press enter - beat 4 renders.

## Beat 4 - Human in the loop

**On screen:** the HITL panel, inviting a human to add a note to the
briefing.

**Do:** type nothing, touch no files - press enter. The run applies the
scripted note itself.

**On screen:** the underwriter's note from the fixture, marked as
scripted, and the token counts moving.

**Say:** **"Now the human contributes. In production this is an
underwriter typing in their own editor - here the run applies a scripted
note so the demo is reproducible, and it says so on screen. Look at what
the note adds: a broker call this morning, knowledge no agent had. And
look at what it took to add it: nothing. No import, no re-indexing, no
pipeline. The file is the store, so the next read simply has it - the
token counter just proved that."**

**Do:** switch to Obsidian, show the note at the end of `briefing.md`, point
at the wikilink inside it.

**Say:** **"The underwriter just connected two cases by hand - that link
becomes a graph edge on the next rebuild."**

**Do:** still in Obsidian, click into `platform-ic/skills/`, ten seconds.

**Say:** **"Skills enter the wiki the same way - a person writes markdown,
the platform inherits it."**

**Do:** switch back to the terminal, press enter - beat 5 renders.

## Beat 5 - Compound

**On screen:** the precedent query as it stood, then the drafted lesson
L-002 with "nothing written yet", then an explicit approval pause.

**Do:** stop at the pause. Let the room read the lesson, or read it aloud.

**Say:** **"This is the strictest gate in the architecture. A write into
`platform-ic` changes what every future case in this class retrieves, so the
lesson goes on screen first and a human approves it after reading it,
never before. There is no edit button here on purpose - if the text is
wrong, you reject it and fix it in the markdown, which you just saw takes
nothing."**

**Do:** press enter to approve.

**On screen:** the two writes, the rebuild with new counts, the same
precedent query returning 10 -> 11 with the new results named.

**Say:** **"One rebuild, and the same precedent query now returns the new
lesson - and look closer: the case we just assessed is itself in the top
results. The submission that walked in this morning is already precedent
for the next one. That is knowledge compounding, measured."**

**Do:** switch to Obsidian, graph view. L-002 is connected to the case
cluster, and the underwriter's hand-typed link is now an edge.

**Say:** **"Same markdown, two projections: the vault graph a person
walks, and the knowledge graph the agents traverse. That is the
architecture in one picture."**

**Do:** switch back to the terminal - the closing panel is already on
screen, no enter needed.

## The close

**On screen:** the final panel - 12 tool calls, 4 model calls, 12,759
tokens, 4 wiki writes.

**Say:** **"Every number on this screen is auditable - the trace is
append-only JSONL, and what you watched is literally a replay of it. One
thread we left open deliberately: the assessment says refer, and resolving
that is a human decision that would land as the next numbered record in
`decisions.md`. The system drafts; people decide."**

## Questions you may get

**Where do the index numbers come from (33/35/46/78)?** They are the census of
the derived indexes: 33 markdown files parsed, cut into 35 retrieval
chunks (most files are single-chunk), one embedding per chunk, and a graph
of 46 nodes and 78 edges built from the files, their declared entities,
and their links. The counts are deterministic - same files, same numbers
every rebuild - and the demo moves them live: after the case closes they
read 36/41/50/105, and every delta is a file, chunk, node or edge you
watched being created.

**Why a terminal and not a UI?** The terminal is the engineering view: real
tool calls, real arguments, nothing hidden. Underwriters would live in the
wiki surface and their own tools. Any front-end binds to the same MCP
contracts and the same trace stream you watched, which is why building one
is additive, not a rewrite.

**Is this agent-to-agent (A2A)?** No, deliberately. MCP is the agent-to-tool
boundary - governed access to knowledge - and that is what is being shown.
A2A belongs where opaque agents cross process or organizational lines,
which in this architecture is the seam between the main orchestrator and
functional orchestrators if those ever become separately deployed services.
One process, one graph, no such seam - wiring A2A into it would be protocol
theater. The typed contracts between agents keep that door open.
The same boundary rule covers reuse: an agent published beyond its own
swarm - utility agents especially - carries an agent card in a registry
and is discovered and consumed via A2A; nothing in this demo is published,
which is why the protocol is out of scope here.

**Why is the validator not another model call?** Because governance checks
should say the same thing every time. The cross-validation is rule-based
and deterministic: every finding must carry a verified citation, and
contradictory gradings raise a flag for a human.

**What does `(unverified)` mean if it appears in a draft?** An agent cited a
source that retrieval never gave it, and the guardrail stripped the
citation at the source. Fabricated provenance dies before human review,
visibly.

**Why SQLite and not a graph database?** The stores sit behind protocols; the
demo earns nothing from running database containers on a laptop. Swapping
in a native engine changes the store implementation and no caller.

**Which vendors is this built on?** The architecture is deliberately
vendor-agnostic: vector store, knowledge graph, and LLM provider are each
behind a single seam and replaceable. Naming the current picks is a
deployment conversation, not an architecture one.

**Is the data real?** Entirely fictional - two invented companies and an
invented claim history, consistent end to end. No client data has ever
touched this system.

**What would it take to make this real?** The wiki conventions, the MCP tool
contracts, the guardrails and the trace format are the architecture - they
carry over as-is. Production adds scale (native stores behind the same
protocols), identity and access, and the main orchestrator layer this demo
stands in for.