# llm-wiki-schema

A schema for an LLM-maintained wiki across a constellation of related repos.

You read it, an agent writes it, and a schema keeps the agent a disciplined maintainer instead of
a generic chatbot. This repo is the schema and the reasoning behind it. It is not my wiki, that
one stays private, it is the thing that makes mine work and that you can point at your own repos.

I run this over four repos that overlap and inherit from each other: a model training pipeline, a
public demo of the same models, a home automation agent, and the product site that sells the
hardware. The problem it solves is not "I cannot find my notes." It is that four repos drift
apart, and the drift is invisible until something breaks in the field.

## The claim

Retrieval over a corpus you own and curate does not need an embedding index. It needs a schema.

I am not against RAG. I chose a different index. An embedding index is automatic, lossy, and
semantic. This one is curated, structured, and explicit, and it holds one thing embeddings do not
give you for free: a canonical statement of a shared fact, so that two repos disagreeing about it
becomes a visible, flagged state instead of a silent one.

That distinction is not academic. It caught a real bug that retrieval structurally could not.
[The full story is in docs/why-a-curated-index.md](docs/why-a-curated-index.md).

## The three layers

1. **Raw sources**, read but never edited from the wiki: the repos themselves. Their code and
   their per-repo agent instructions are the source of truth for how each repo works internally.
2. **The wiki**, LLM-written: the connective tissue. What each project is, how they relate, the
   shared entities they inherit from each other, and the reasoning behind divergences.
3. **The schema**, [SCHEMA.md](SCHEMA.md): conventions plus the ingest, query and lint workflows.

## The cardinal rule

Hold only what is cross-cutting and not cheaply re-derivable from a single repo's code.

Relationships, shared entities, canonical definitions, and the *why* behind divergences. Never
file trees, API signatures, or build commands, those go stale fastest and are owned by the repo
they live in. If a fact lives entirely inside one repo and that repo's docs already state it, link
down to it, do not copy it up.

This rule is the whole design. It is what keeps the corpus small enough that one person can
actually curate it, and it is why the thing fits in a context window instead of needing to be
chunked.

## Ligaments

The part I have not seen elsewhere. `ligaments.md` holds the **directed edges** between projects:
who feeds, inherits, sells, or deploys whom. Each project page links back to it.

It is a hand-maintained knowledge graph, and it is where the value concentrates, because the edges
are exactly the facts that live in no single repo and that nobody writes down. When a shared data
file is vendored from one repo into another, that is an edge. When two projects run on the same
machine and share a class of bug, that is an edge. When one project's model is a twin of another's,
that is an edge, and the places they diverge are the most valuable lines in the wiki.

## Flagging uncertainty

Two markers, used liberally:

- `VERIFY:` for believed-but-unconfirmed.
- `DIVERGENCE:` for a known mismatch between repos, with whether it is intentional.

The wiki is allowed to be unsure. It is not allowed to be quietly wrong. This is the same stance
the rest of my work takes: a system that abstains beats one that bluffs.

## Operations

- **Ingest**, after meaningful cross-project work. Update affected pages, refresh links, update
  the index, append a dated line to the log. One pass.
- **Query**. Answer from the wiki first. If the answer required digging into a repo, file the
  finding back as a page or an edit, so the next query is cheap.
- **Lint**, periodic. Hunt `DIVERGENCE:` and `VERIFY:` items, stale claims, orphan pages, missing
  back-links. Resolve or re-flag.

## Where this breaks

One curator plus an agent can hold context because the curator has read everything. Add a thousand
actors and it does not fail from missing documents, it fails from **semantic collision**, the same
term carrying two definitions with both sides confident.

Keyword detection does not catch that, and neither do embeddings. What does is making canonical
statements executable, so drift fails a build instead of waiting for a reviewer.
[docs/scaling.md](docs/scaling.md) works through it, including the parts I have not built.

## The linter

[`lint/wikilint.py`](lint/) is the first piece of that, built and running. It checks the wiki
against the repos it describes and exits non-zero on conflict, so it sits in CI.

The check that matters most is `unresolved-downstream`: the wiki declares a topic resolved while a
repo that cites it still carries an open `DIVERGENCE:` marker. That is not a hypothetical, it is
the first thing it found when I pointed it at my own constellation. Someone decided, and the code
never got the memo. A prose resolution is a claim about the future, and only a test makes it a
claim about the present, which is what `unpinned-decision` is for.

Stdlib only, no dependencies, 12 tests. Checks and config format: [lint/README.md](lint/README.md).

## Using it

Copy [SCHEMA.md](SCHEMA.md) into a new repo as your agent instructions file, adjust the layout
section to your projects, and start with `ligaments.md`. The edges are the reason to do this at
all, so if you only write one page, write that one.

## License

Apache 2.0.
