# wikilint

A conflict linter for an LLM-maintained cross-project wiki.

It is not a search tool. It looks for places where the wiki and the repos it describes **disagree**,
which is the failure mode that costs you at a repo boundary: one term, two definitions, both sides
internally consistent, no disagreement visible on the surface.

Stdlib only, no dependencies. Exits non-zero at or above `--fail-on`, so it runs in CI.

```
python3 lint/wikilint.py -c wikilint.json
python3 lint/wikilint.py -c wikilint.json --json --fail-on warn
python3 lint/wikilint.py -c wikilint.json --only unresolved-downstream
```

## Why a linter and not a search

The bug that motivated this: two repos both computed growing-degree-days, both said "GDD", and
each accumulated from a different start date. A keyword search matches both and reports success,
because by its own criteria it succeeded. An embedding index scores the two passages as highly
similar, which is correct and is also the problem. Similarity is not agreement.

Nothing in a retrieval index represents *"these two things claim to be the same and are not."*
That is a consistency check, and consistency checks are closer to type-checking than to search.

## The checks

| Check | Severity | What it means |
|---|---|---|
| `unresolved-downstream` | error | The wiki declares a topic RESOLVED, but a repo that cites that page still carries an open `DIVERGENCE:`/`VERIFY:` marker. Someone decided, and the code never got the memo. |
| `unpinned-decision` | warn | A canonical page is declared RESOLVED, but no *test* anywhere references it. A prose resolution is a claim about the future; only a test makes it a claim about the present. |
| `stale-verify` | warn | A dated `VERIFY:` has been open longer than `stale_verify_days`. Believed-but-unconfirmed has a shelf life. |
| `orphan-page` | warn | A page not linked from the index. Unindexed pages stop being read, then stop being true. |
| `dangling-canonical` | info | A canonical page no repo cites. Either the convention is dead, or the repos that should honour it never got wired up. |
| `broken-link` | info | A `[[link]]` with no page behind it. Intentional TODO markers are fine, so this is a to-write list rather than an error. Links inside code spans are ignored, since a page documenting the syntax is not making a link. |

## How the two sides get connected

With no retrofit, if you already write cross-references in prose.

- **Wiki side.** A resolution is a line matching `RESOLVED` followed by a date or a colon. It
  applies to whatever it `[[links]]`, or to its own page if it links nothing. Journal pages
  (`index.md`, `log.md` by default) never resolve themselves, since they record other pages'
  decisions.
- **Repo side.** Any file containing `DIVERGENCE` or `VERIFY:` is scanned for a wiki page
  reference (`<wiki-dir>/path/page.md`) within a window around the marker, falling back to the
  file. That reference is the join key.

So a docstring like this is enough to wire a module into the linter:

```python
"""
DIVERGENCE (open, 2026-07-26): this module accumulates from a different start date.
Canonical convention: my-wiki/entities/units-convention.md
"""
```

## Config

`wikilint.json`, next to wherever you run it. Only `wiki` and `repos` are required.

```json
{
  "wiki": "~/path/to/my-wiki",
  "index": "index.md",
  "journal_pages": ["index.md", "log.md"],
  "canonical_dirs": ["entities"],
  "stale_verify_days": 90,
  "repos": [
    {"name": "service-a", "path": "~/code/service-a"},
    {"name": "service-b", "path": "~/code/service-b"}
  ]
}
```

`wiki_ref_patterns` is derived from the wiki directory name and can be overridden. It is a list of
regexes whose last capture group is the page slug.

**Your config points at real paths, so keep it out of a public repo.** Commit
`wikilint.example.json` and gitignore the real one.

## Running it in CI

See [`.github/workflows/wikilint.yml`](../.github/workflows/wikilint.yml). Checking out sibling
repos is the part that needs thought, and the honest answer is that cross-repo CI is harder than
single-repo CI. Two shapes work:

1. **The wiki publishes.** Canonical assertions become a versioned artifact each repo depends on,
   and each repo's own CI checks itself. Clean, but a knowledge layer that can break your build is
   one people route around.
2. **Each repo fetches.** Repos pull current assertions at CI time. No dependency edge, but the
   checks are only as fresh as the fetch, and a repo can quietly stop fetching.

The workflow here does the simplest useful version: it runs in the wiki's own repo and checks out
the repos it describes. That works when they are all visible to one token.

## Tests

```
cd lint && python3 -m unittest test_wikilint -v
```

12 tests, no dependencies. They build a synthetic wiki and repo in a temp dir, so they do not
depend on anyone's filesystem.

## What it does not do

- It does not compare *values* across repos yet. Catching `BASE_TEMP = 50` against `base = 45` is
  the obvious next check and it needs a declaration format for assertions.
- It does not understand prose. If a repo diverges without writing a marker, the linter cannot
  know, and that is a real limit: it enforces a convention rather than discovering violations of
  one.
- It is a consistency checker, not a retrieval system. It will not find you the right page.
