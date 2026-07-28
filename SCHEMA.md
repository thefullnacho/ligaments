# Wiki schema and maintenance rules

*Drop this in as your agent instructions file (`CLAUDE.md`, `AGENTS.md`, or equivalent) at the
root of a wiki repo. Adjust the Layout and Raw sources sections to your own projects. Everything
else is portable as written.*

---

This repo is the **cross-project knowledge layer** for the `<constellation name>` constellation.
It is an LLM-maintained wiki: you read it, the agent writes it, and this schema keeps the agent a
disciplined maintainer instead of a generic chatbot.

## The three layers

1. **Raw sources** (read, never edited from here): the project repos themselves.
   - `<path/to/repo-one>`
   - `<path/to/repo-two>`

   Their code and per-repo instruction files are the source of truth for *how each repo works
   internally*.
2. **This wiki** (LLM-written): the connective tissue. What each project IS, how they relate, the
   shared entities they inherit from each other, and the decisions behind divergences.
3. **The schema** (this file): conventions plus the ingest / query / lint workflows below.

## The cardinal rule, what belongs here vs. not

Hold only what is **cross-cutting and not cheaply re-derivable from a single repo's code**:
relationships, shared entities, canonical definitions, and the *why* behind divergences.

**Do NOT** restate file trees, API signatures, or build commands. Those go stale fastest and are
owned by each repo's code and instruction file. If a fact lives entirely inside one repo and that
repo's docs already state it, link down to it, do not copy it up.

When in doubt, ask: would this be wrong in three weeks if someone refactored a repo without
touching the wiki? If yes, it belongs in the repo, not here.

## Layout

- `index.md` — the catalog. Every page with a one-line summary. Keep it current.
- `ligaments.md` — the directed edges between projects (who feeds / inherits / sells / deploys
  whom). This is the heart of the wiki.
- `projects/*.md` — one page per repo: what it is, its boundary, its status, its edges.
- `entities/*.md` — shared things that live in more than one repo. The canonical statement of a
  shared fact lives here, and repos defer to it.
- `log.md` — append-only. Every ingest, decision, and lint pass gets a dated line.

## Conventions

- Cross-link liberally with `[[page-name]]` (filename, no path or extension). A link to a page
  that does not exist yet is fine, it is a TODO marker, not an error.
- Convert relative dates to absolute (YYYY-MM-DD). "Last week" is worthless in six months.
- Flag uncertainty explicitly:
  - `VERIFY:` believed but unconfirmed.
  - `DIVERGENCE:` a known mismatch between repos, plus whether it is intentional.
- Keep pages short. A page that needs scrolling is two pages.
- One canonical statement per shared fact. If two pages state the same thing, one of them is
  wrong and you will not find out which until it matters.

## Operations

### Ingest
After meaningful cross-project work: update the affected project and entity pages, add or refresh
`[[links]]`, update `index.md`, append a `log.md` line. One pass.

### Query
Answer from the wiki first. If the answer required digging into a repo, **file the finding back**
as a page or an edit, so the next query is cheap. A query that does not improve the wiki was a
wasted trip.

### Lint
Periodic health check. Hunt for:
- open `DIVERGENCE:` and `VERIFY:` items
- stale claims (dates, statuses, "in flight" things that landed)
- orphan pages, not linked from `index.md`
- missing back-links, a page referenced by an edge but not linking to `ligaments.md`

Resolve or re-flag each one in `log.md`.

## Divergences are the point

When two repos disagree about a shared fact, that is not a bug in the wiki, it is the wiki doing
its job. Record it, decide a lane, and write down which repo has to change and why.

The failure mode this catches is the expensive one: two repos computing **different quantities
under the same name**, both internally consistent, silently disagreeing across the boundary. No
single-repo test finds that, because inside each repo the code is correct.

Once a divergence is resolved, pin the decision with a test in the repo that has to honour it.
A canonical statement that is only prose will drift back. See `docs/scaling.md`.
