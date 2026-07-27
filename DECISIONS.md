# Decisions

Why the demo is built the way it is. The repo keeps a decisions record the
same way every case wiki does - the demo practices its own architecture.
Entries are appended as the build progresses and never rewritten after the
fact; if a decision is reversed, the reversal gets its own entry.

## Knowledge base

**Markdown files are the primary store, indexes are derived.** The vector
index and the knowledge graph are disposable and rebuilt from the wiki with
one command. This is the founding claim of the architecture, so the demo has
to live it: at no point does any component hold state that cannot be
regenerated from the markdown.

**SQLite behind store protocols.** A laptop demo earns nothing from running
database containers. Both stores sit behind VectorStore and GraphStore
protocols, so a post-rehearsal swap to a native embedded graph engine stays
contained in stores/ and changes no caller.

**propose_wiki_update() as the fourth MCP tool.** The platform deck shows
write_session_state() on the MCP band, but the demo beats need the wiki
write path: draft assessments landing in briefing.md and decisions.md.
Session state is a platform concern this demo does not exercise.

**Relation names come from the published vocabulary, never from slides.**
The agent build brief asked for GOVERNS and APPLIES_TO, lifted from an
illustrative slide. The vocabulary set-equality test refused them, which is
that test doing its job: nobody invents relations, not even the build
instructions. The published relations stand (in_class, applies_to_class,
has_lesson) and the deck aligns to the code, not the reverse - changing
reality to match an illustration would have meant editing a human-only
vocabulary file and rebuilding the graph for nothing.

## Agent layer

**Orchestration on a graph framework, confined to one file.** The
orchestration layer uses the framework we would reach for in production,
which keeps the demo honest about how this scales - and the compiled graph
mirrors the architecture slide almost literally. The discipline that keeps
the walkthrough readable: only agents/graph.py imports the framework, and it
contains wiring only (state schema, nodes, edges, parallel fan-out).
Specialists and the orchestrator are plain typed functions a client engineer
can read in one sitting. No adapter or companion packages. Layering tests
enforce both confinements: only llm.py imports the provider SDK, only
graph.py imports the framework.

**Agents call the MCP tool functions in-process.** MCP is the contract
boundary here, not a network hop. The tool signatures are exactly the
interface a remote transport would expose; putting HTTP between two modules
of the same process would add latency and demonstrate nothing.

**One specialists.py rather than a file per agent.** Three functions of
roughly forty lines each read better side by side, where it is obvious they
share one contract. At production scale, when each agent grows its own
prompts, config and tests, one module or package per agent is the right
shape. The split trigger is recorded: if the client walkthrough wants to
open exposure_analyst.py next to its slide box, the refactor into
agents/specialists/ with the shared Assessment type in agents/types.py is
mechanical and takes minutes.

**Agents may only cite what they were given.** After every specialist LLM
call, any cited chunk ID or entity ID not present in the retrieved context
is stripped. Fabricated provenance dies at the source instead of surviving
until human review. The first live run demonstrated it: one fabricated
citation was stripped mid-sentence, exactly as designed.

**The strip marker is (unverified), parenthesized.** Cited ids usually sit
inside square brackets, and a bracketed marker landing there would parse as
a wikilink and become a graph edge on the next rebuild. Parentheses cannot
be mistaken for structure. A test pins this.

**The cross validator is rule-based, no LLM call.** Deterministic
validation is a feature twice over: the contradiction flag fires identically
in every rehearsal, and it makes the governance point that consistency
checks do not have to be another model call.

**Case decision records are dated, not numbered.** propose_wiki_update is
the only door into the wiki and it does not open outwards, so the
orchestrator cannot read a decisions file to count existing records. A
draft record is therefore keyed by date, and the human who confirms it
assigns the number. The asymmetry is deliberate: numbering is an act of
human acceptance, not something an agent grants itself.

**Replay is built into llm.py from day one.** Every live completion is
recorded to traces keyed by a stable hash of the request; replay mode
resolves from that record and fails loudly on a miss, and the newest
recording for a key wins so a re-run corrects a stale one. demo.py --replay
becomes a flag rather than a refactor, and a rehearsal can never be sunk by
network or provider trouble.

**Tests fake the completion function; the demo replays real ones.**
Specialists receive complete() as a parameter, so tests inject a
deterministic fake that forces specific branches: a fabricated citation to
prove stripping, an off-vocabulary label to prove the unstated fallback, a
contradiction to fire the validator. Replay mode is the opposite tool, real
recorded completions for the live walkthrough. Same seam, two purposes,
zero network in tests either way.

## Protocol positioning

**MCP in, A2A out, deliberately.** The two solve different problems. MCP is
the agent-to-tool boundary - governed access to knowledge and capabilities -
and that is the thing being demonstrated. A2A is the agent-to-agent boundary
for opaque agents crossing process, team or organizational lines. This demo
has no such line: one process, one graph, shared state. Wiring A2A between
the orchestrator and specialists would be protocol theater. Where it would
legitimately slot in is the Main Orchestrator -> functional orchestrator
seam, if orchestrators ever become separately deployed services or an
external party's agent delegates work into the platform. The typed
Assessment contract between agents already keeps that door open.

## Repo shape

**Flat layout, no src/ nesting.** The demo is small and flat reads better
in a walkthrough. Depth gets added when the code demands it, not before.