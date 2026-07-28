# ligaments

**An LLM-maintained wiki schema for multi-repo codebases: cross-project knowledge management
without RAG or a vector database, plus a CI linter that fails the build when the docs and the code
disagree.**

You read it, an agent writes it, and a schema keeps the agent a disciplined maintainer instead of
a generic chatbot. This repo is the schema, the reasoning behind it, and the linter. It is not my
wiki, that one stays private, it is the thing that makes mine work and that you can point at your
own repos.

I run it over four repos that overlap and inherit from each other: a model training pipeline
([forager_ml](https://github.com/thefullnacho/forager_ml)), a public demo of the same model stack,
a home automation agent ([hestia](https://github.com/thefullnacho/hestia)), and the product site
that sells the hardware the models run on. The problem it solves is not "I cannot find my notes."
It is that four repos drift apart, and the drift stays invisible until something breaks in the
field.

## Why "ligaments"

The name is the idea. `ligaments.md` holds the **directed edges** between projects: who feeds,
inherits, sells, or deploys whom. It is a hand-maintained knowledge graph, and it is where the
value concentrates, because edges are exactly the facts that live in no single repo and that
nobody writes down.

When a shared data file is vendored from one repo into another, that is an edge. When two projects
run on the same machine and share a class of bug, that is an edge. When one project's model is a
CPU twin of another's, that is an edge, and **the places they diverge are the most valuable lines
in the wiki.** A repo documents itself. Nothing documents the seams, and the seams are where the
expensive bugs live.

If you only write one page, write that one.

## The claim

Retrieval over a corpus you own and curate does not need an embedding index. It needs a schema.

I am not against RAG. I chose a different index. An embedding index is automatic, lossy, and
semantic. This one is curated, structured, and explicit, and it holds one thing embeddings do not
give you for free: a canonical statement of a shared fact, so two repos disagreeing about it
becomes a visible, flagged state instead of a silent one.

That is not academic. It caught a real bug that retrieval structurally could not:
[docs/why-a-curated-index.md](docs/why-a-curated-index.md).

## The three layers

1. **Raw sources**, read but never edited from the wiki: the repos themselves. Their code and
   per-repo agent instructions are the source of truth for how each repo works internally.
2. **The wiki**, LLM-written: the connective tissue. What each project is, how they relate, the
   shared entities they inherit, and the reasoning behind divergences.
3. **The schema**, [SCHEMA.md](SCHEMA.md): conventions plus the ingest, query and lint workflows.

## The cardinal rule

Hold only what is cross-cutting and not cheaply re-derivable from a single repo's code.

Relationships, shared entities, canonical definitions, and the *why* behind divergences. Never
file trees, API signatures, or build commands, those go stale fastest and are owned by the repo
they live in. If a fact lives entirely inside one repo and that repo's docs already state it, link
down to it, do not copy it up.

This rule is the whole design. It is what keeps the corpus small enough for one person to actually
curate, and it is why the thing fits in a context window instead of needing to be chunked.

## Flagging uncertainty

Two markers, used liberally:

- `VERIFY:` for believed-but-unconfirmed.
- `DIVERGENCE:` for a known mismatch between repos, with whether it is intentional.

The wiki is allowed to be unsure. It is not allowed to be quietly wrong. Same stance as the rest
of my work: a system that abstains beats one that bluffs.

## Operations

- **Ingest**, after meaningful cross-project work. Update affected pages, refresh links, update
  the index, append a dated line to the log. One pass.
- **Query**. Answer from the wiki first. If the answer required digging into a repo, file the
  finding back as a page or an edit, so the next query is cheap.
- **Lint**. Continuous and executable rather than periodic and manual. See below.

## The linter

[`lint/wikilint.py`](lint/) checks the wiki against the repos it describes and exits non-zero on
conflict, so it sits in CI. Stdlib only, no dependencies, 12 tests.

The check that matters most is `unresolved-downstream`: the wiki declares a topic resolved while a
repo that cites it still carries an open `DIVERGENCE:` marker. That is not hypothetical. It is the
first thing the linter found when I pointed it at my own constellation, in a module whose
resolution I had written two days earlier and never implemented. A prose resolution is a claim
about the future; only a test makes it a claim about the present, which is what
`unpinned-decision` is for.

Checks and config: [lint/README.md](lint/README.md).

## Where this breaks

One curator plus an agent can hold context because the curator has read everything. Add a thousand
actors and it does not fail from missing documents, it fails from **semantic collision**: the same
term carrying two definitions, both sides confident.

Keyword detection does not catch that, and neither do embeddings. What does is making canonical
statements executable, so drift fails a build instead of waiting for a reviewer.
[docs/scaling.md](docs/scaling.md) works through it, including the parts I have not built.

## Using it

Copy [SCHEMA.md](SCHEMA.md) into a new repo as your agent instructions file, adjust the layout
section to your projects, and start with `ligaments.md`.

## Who wrote this

Alexandre de Brantes. I build [HomesteaderLabs](https://homesteaderlabs.com), an offline-first
edge-AI company, solo: the models, the device, the software, and the go-to-market. Open weights on
[Hugging Face](https://huggingface.co/HomesteaderLabs), code at
[github.com/thefullnacho](https://github.com/thefullnacho).

This schema exists because running four interlocking repos alone means nobody else is going to
notice when two of them quietly stop agreeing.

## License

Apache 2.0. `SCHEMA.md` is meant to be copied into your own repo and edited freely, so treat that
file as a template with no attribution ceremony expected. See [NOTICE](NOTICE).
