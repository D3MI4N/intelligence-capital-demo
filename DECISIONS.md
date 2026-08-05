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

## The demo driver

**demo.py is the Main Orchestrator's stand-in, and only its stand-in.** It
receives the task, hands it to the Risk Assessment orchestrator, and does the
two things the platform reserves for a human: accepting an edit, and closing a
case. Everything between those is the agent layer running unmodified, which is
the point - a driver that reached inside the run to make the demo prettier
would be demonstrating the driver.

**The beats are streamed out of the compiled graph, not reassembled from the
step functions.** The presenter pauses between beats, and a call that only
returns when it is over cannot be paused. graph.py gained one function that
yields each node's result as it lands; the state schema, the nodes and the
edges are untouched, and the three specialists still fan out in parallel on
stage rather than in a story about the stage.

**The demo echoes the trace, not the agents.** Every tool call on screen is
read back from traces/ after the beat that made it, with the arguments the
trace recorded and the order restored from the tool's own signature. Two
things follow: the demo cannot show a call that was not traced, and what the
room sees is exactly what an auditor would read the next morning. Retrieval
scores were added to the search trace for this - a retrieval audit that cannot
say how close the cited chunk was is missing the number that matters.

**Case close is a ceremony, performed by demo.py, through propose_wiki_update.**
Promoting a lesson changes what every future case in the class retrieves, so it
is a decision and not an agent step. It is still written through the tool, with
the same guardrails and the same trace line: agents never touch storage, and
nothing else in the repo does either.

**The ceremony runs behind an approval gate, and the gate opens after the
reading.** A write into platform-ic is the strictest human gate in the
architecture - it is the one write that changes retrieval for cases nobody has
opened yet - so beat five puts the drafted lesson on screen, waits for the
presenter, and only then writes. A gate that is cleared before the room has read
what it approves is a gate in the ordering only. --no-pause skips the wait the
same way it skips the ones between beats: that flag is for rehearsing alone, and
it is not the demo.

**The lesson text here is scripted; the gate is what generalises.** The demo
carries L-002 as a constant because beat five rebuilds the indexes and the
recorded embeddings have to match the corpus that comes out, down to the
sentence. In production the case-close agent drafts that text from the case and
a human approves it at this same gate - the drafting seat moves, the gate does
not.

**The gate is approve-or-stop, with no edit path.** Offering "edit the lesson
first" would put the human back in the drafting seat at the moment they are
being asked for a decision, and it would mean the text that gets promoted is one
no agent proposed and no draft trace explains. Approve and the ceremony runs as
shown; stop and nothing is written, the lesson stays a candidate in the case
wiki, and the human edits the markdown there - which is the write path beat four
already demonstrates. Keeping the gate binary keeps it auditable: the trace
records a promotion or it records nothing.

**The compounding is proved on the graph, not on the search.** A search with a
fixed top_k returns the same number of hits before and after a promotion, so a
demo that counted search results would show 5 -> 5 and claim compounding. The
new lesson hangs off the risk class instead: the case's own lessons.md carries
L-002, the rebuild derives Case -> has_lesson -> Lesson from it, and the
precedent traversal from RiskClass:cyber-logistics comes back with one more
entity than before. Nobody points the next submission at the promoted file; the
graph does. The demo reports both counts so the room can see which one moved.

**A replayed run writes the date of the run it replays.** Beat 5 rebuilds every
index from the markdown, and the markdown by then contains the records beat 3
wrote, dated. A replay that dated its own records today would chunk to text the
recorded embeddings never saw, and the rebuild would miss on every changed
chunk. So a live run records its date next to its completions, and a replay
reads it back. Replaying a run means replaying all of it.

**Embeddings record and replay exactly like completions.** Every search embeds
its query and every rebuild embeds the corpus, so replay without them was
replay that still needed the network at two of the five beats. Same shape:
keyed by model and text, newest recording wins, a miss names the text and
refuses rather than inventing a vector. Keyed per text rather than per batch,
so a rebuild that groups the corpus differently still resolves.

**The human edit is scripted in replay, and the screen says so.** Live, the
presenter types it in Obsidian. Replayed, it comes from a checked-in fixture,
because the rebuild in beat 5 has to produce the corpus the embeddings were
recorded from and a sentence typed twice is not the same sentence. Either way
it is a direct file write: the wiki rules say direct writes are for humans, and
this beat is the one where a human writes. The trace records that the demo
applied it, marked scripted or typed.

## Carry-overs from the first live run

**Ask before stripping.** The strip that removes an id the agent was not given
stays exactly as it was, but the specialists and the drafter are now told to
cite only ids that appear verbatim in what they were handed. The guardrail is
what makes the demo safe to show; asking first is what makes it rarely fire.

**Normalisation happens once, at the write-back boundary, and is counted.** The
model returns non-breaking hyphens and em dashes that look identical on screen
and break a grep for an identifier. They are rewritten into house style on the
way into the wiki - not in the specialists, not in the tool, at the one point
where composed text becomes a write - and the number of characters replaced
goes on the trace line. A silent cleanup is a cleanup nobody can audit.

**No open-questions section when there are no open questions.** The drafter
used to be handed an empty cross-validation block and asked to end with the
open questions; it dutifully wrote a paragraph explaining there were none. An
empty heading is an invitation to fill it, so when the validator comes back
clean the section and the instruction are both left out.

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
## The blessed recording

**The recording the demo replays from is committed; traces/ stays gitignored.**
The machine that presents the demo is not the machine that recorded it, and a
replay that depends on a directory git never carried is a replay that only
works on one laptop. So traces/ keeps its job - the live stream, everything the
rehearsals on this machine wrote - and fixtures/recording/ holds the blessed
copy that travels with the repo. Committing the vectors costs about a megabyte,
which is the price of a walkthrough that cannot be sunk by a guest network or
by presenting from a different machine.

**Blessing is compaction, not copying.** demo.py bless takes the current traces
and keeps the newest entry per key, dropping everything it superseded - the
same rule replay resolution already applies when it reads the newest recording
of a key. A rehearsal recorded over a week is mostly superseded entries; what
gets committed is one run's worth. It refuses on an empty or missing file
rather than blessing half a run, because a recording with no embeddings replays
until the first search and then stops, in front of the client.

**Compaction orders by newest entry, and that is load-bearing.** demo_runs.jsonl
is read from the end - a replay writes the date of the run it replays - so
installing the recording onto a machine whose own live runs are more recent has
to leave the blessed run last. Keeping an entry in its original position would
have left a later local run answering for a recording it has nothing to do with,
and every changed chunk would miss.

**Installing happens in reset --replay, so llm.py keeps one source.** The
alternative was teaching the replay path a second location to look in, which
would put a fallback in the one module the whole demo trusts to be offline.
Instead the recording is installed into traces/ after the wiki restore and
before the rebuild, and everything downstream is unchanged: agents/llm.py still
reads one path and still takes the newest recording of a key. A live reset
installs nothing, because live is how a recording gets made.

**Installing merges rather than overwrites.** Whatever this machine recorded for
keys the recording does not cover survives, the recording wins every key it does
cover, and the file is compacted on the way in, so it does not grow by a whole
run every reset. What is not blessed is the daily trace file: that is the audit
stream a run produces, not something it consumes, and a replayed run writes its
own.

## The client review - 2026-08-05

**The entry point is named after the thing it runs: intelligence_capital_demo.py.**
"demo.py" is what a repo calls a script nobody has decided about yet, and it is
the first line of the run on a projector. The rename costs one command and every
reference in the manual, the README and the tests. demo.py stays as a two-line
shim that names the new file and exits nonzero, because the presenter's fingers
know the old name and a silent absence at the start of a walkthrough is worse
than an error that says where to go.

**"Beat" left the screen and kept its job in the code.** It is stage vocabulary
- useful to whoever builds the run, meaningless to an underwriter reading a
terminal - so the panels are titled for what they do and where they sit in the
swarm flow the deck already shows: ORIENT is step 2, RETRIEVE is steps 3-5,
WRITE BACK is steps 6-8, HUMAN IN THE LOOP is step 9, COMPOUND is where the case
closes. The closing panel is DONE and carries no number at all, because "BEAT 0"
was only ever a way of reusing the panel. Identifiers, function names and test
names keep the word: renaming them would be churn in exchange for nothing, and a
test asserts the room never sees it.

**The census names the platform and breaks the graph down live.** Four rows that
said documents, chunks, nodes, edges now say IC Wiki Documents, IC Embedding
Chunks and IC Knowledge Graph, which is what they are called everywhere else the
client meets them. Under the graph, the edges are split into the three kinds they
actually are - relations between entities, references from a document to an
entity, links from one file to another - counted off the graph store at the
moment the table is printed, never written down. That is what makes the
breakdown survive the rebuild at case close, where all three kinds grow: 28/42/8
of 78 before, 37/54/14 of 105 after, and nobody has to remember to update a
number. The third row is named for what it holds - wikilinks and the locator
lines a source note carries back to its raw document - because the Obsidian vault
graph draws the wikilinks among them, and the closing line of the demo makes that
claim out loud.

**The echoed call names the agent from the trace, not from the order.** The three
specialists run in the same superstep and their calls land interleaved, so the
call sitting in the second position on screen belongs to whichever agent got
there second. The tools therefore record their caller: the context carries an
optional agent name, and the trace line carries it as a field of its own rather
than as another argument, so the arguments on the line stay the arguments of the
call and a line written before the field existed still reads exactly as it did.
Where a line names nobody, the echo falls back to the phase it was read in. What
the room sees is what an auditor would read the next morning, which was already
the rule - this only extends it to who asked.

**A pasted note is the scripted edit.** The human edit was either applied from
the fixture or typed, and typed meant a warning that the recordings no longer
match. That left the presenter who wants the edit to visibly happen in Obsidian
with no good option. So the edit is compared with the fixture, forgiving what an
editor changes on its own - line endings, whitespace at the end of a line - and a
match is recorded as the scripted edit, on the same trace line, with no warning.
Anything else keeps the warning it always had, because it is the same fact it
always was: a sentence the recordings have never seen.
