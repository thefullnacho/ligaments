# Why a curated index instead of an embedding index

Short version: I am not against RAG. I chose a different index, and I chose it because my
expensive problem was not recall, it was drift.

## The bug

I run two projects that both compute growing-degree-days. One is a home automation agent that
watches for pest emergence windows and pushes an alert when one opens. The other is a content
pipeline that publishes the pest thresholds those alerts fire against.

Growing-degree-days are an accumulation. You pick a base temperature, you pick a start date, and
you add up the daily heat above that base from the start date forward. Both halves of my system
used the same base. They did not use the same start date.

The agent accumulated from an **observed biofix**, the last spring frost it found in the weather
archive for my location, April 21 that year. The published thresholds it was comparing against
assume accumulation from **January 1**. On the same day, in the same place, those two conventions
produced 1500 and 1608. Roughly 108 degree-days apart, which meant every pest window opened late,
by a margin that shifts year to year with the weather.

Both codebases were internally correct. Both had passing tests. The agent computed its own
quantity accurately and the thresholds were accurate for theirs. The error lived entirely in the
seam, where one repo's number was compared against another repo's number as though they were the
same kind of thing. Nobody wrote down that they were not.

## Why retrieval would not have found it

The obvious objection is that a decent search over both repos would have surfaced this. It would
not have, and the reason is specific.

**Both repos say "GDD."** The vocabulary matched perfectly. That is exactly why the bug survived,
the words agreed while the definitions did not. A keyword search returns both passages and reports
success, because by its own criteria it succeeded.

Embeddings do worse, not better. A vector search scores those two passages as highly similar,
because they *are* highly similar, they are two descriptions of degree-day accumulation. High
similarity is the correct answer and it is also the problem. Similarity is not agreement. Nothing
in an embedding index represents "these two things claim to be the same quantity and are not."

That is the general shape. The failure mode that costs you at the boundary between repos is not a
missing document, it is **semantic collision**: one term, two definitions, both sides confident,
no disagreement anywhere on the surface.

## What the schema does instead

The wiki forces a **single canonical statement** of any fact shared across repos, and gives
disagreement an explicit representation: a `DIVERGENCE:` marker that says these two repos are
mismatched, and whether that is on purpose.

That is the whole mechanism. It is not clever. It works because it makes an absence into a
presence, an unwritten assumption becomes a page that either exists or does not, and two repos
disagreeing becomes a flagged state rather than a silent one.

The divergence got caught, a convention page now owns the definition with sourced thresholds and
citations, and the losing repo kept its original figure under a different name, because it was a
perfectly good quantity, it just was not the one the thresholds meant.

## The honest boundary

This works because I am one curator who has read everything, over a corpus of about a megabyte.
Both of those matter.

- **Curation cost scales with corpus size and with the number of writers.** At a thousand actors,
  nobody has read everything, and the discipline that makes the cardinal rule work stops being
  enforceable by good intentions.
- **A wiki only contains what somebody decided to write down.** Real retrieval problems are often
  discovery problems: the support ticket from eight months ago, the one clause in the one contract
  that nobody knew to look for. Curation has nothing to say about that, and an embedding index
  over everything genuinely does.
- **No semantic search over documents I have never read.** That is a real capability I gave up.

So the honest framing is not that embeddings are obsolete. It is that they solve a compression
problem, corpora that do not fit in context, and when your corpus does fit, chunking discards
structure to solve a problem you no longer have.

## The precedent worth knowing

The strongest evidence for this is not my project. Coding agents do retrieval over large codebases
by search and file reads, not by embedding the repo. Claude Code greps. That is a deliberate
design choice by people who could trivially have shipped a vector index, and it points at the same
conclusion: when you can navigate structure directly, an approximate semantic index is a downgrade.

## Where it goes next

The boundary above is real, and it is not the end of the argument. Making canonical statements
executable, so that drift fails a build rather than waiting for a reviewer, is how the curation
cost stops scaling with the number of actors. That is [scaling.md](scaling.md), including the
parts I have not built yet.
