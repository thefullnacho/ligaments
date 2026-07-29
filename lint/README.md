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
| `config-error` | error | A configured repo path does not exist, so that repo was never scanned. Reported loudly, because the alternative is failing **open**: every other check silently passes and the report reads clean for a repo nobody looked at. False assurance is worse than no assurance. |
| `unresolved-downstream` | error | The wiki declares a topic RESOLVED, but a repo that cites that page still carries an open `DIVERGENCE:`/`VERIFY:` marker. Someone decided, and the code never got the memo. |
| `constant-drift` | warn | The same UPPER_SNAKE constant holds different literal values in different repos. The only check that **discovers** a divergence rather than enforcing an annotation someone already wrote. |
| `unpinned-decision` | warn | A canonical page is declared RESOLVED, but no *test* anywhere references it. A prose resolution is a claim about the future; only a test makes it a claim about the present. |
| `broken-path` | warn | The wiki cites a repo-relative file path that exists in no configured repo. The cardinal rule says link down to the repo rather than copy facts up, so rotted links turn that rule into a liability. |
| `unfilled-placeholder` | warn | Template text shipped as though it were content: `[yyyy]`, `<path/to/...>`, `your-org`, `TBD`. |
| `stale-verify` | warn | A dated `VERIFY:` has been open longer than `stale_verify_days`. Believed-but-unconfirmed has a shelf life. |
| `orphan-page` | warn | A page not linked from the index. Unindexed pages stop being read, then stop being true. |
| `moved-path` | info | A cited path is wrong, but that filename exists elsewhere. Usually a move the wiki did not follow. |
| `dangling-canonical` | info | A canonical page no repo cites. Either the convention is dead, or the repos that should honour it never got wired up. |
| `broken-link` | info | A `[[link]]` with no page behind it. Intentional TODO markers are fine, so this is a to-write list rather than an error. Links inside code spans are ignored, since a page documenting the syntax is not making a link. |

### On `constant-drift`, which is the interesting one

Every other check needs a human to have written a marker first. This one does not, so it is the
only place the tool finds something nobody already knew.

**Scope comes from the wiki.** A constant is compared precisely because the wiki named it, which
is what "canonical" means here. Constants the wiki never mentions are not its business, and that
one rule removes almost all the noise a naive cross-repo grep would produce.

Two deliberate limits. It compares **literals only**: `BASE = 50` against `BASE = 45` is a real
finding, while `float(os.environ.get("X", "50"))` against `float(os.getenv("X", "50"))` is not
worth guessing about, and guessing is how a linter gets muted. And it **skips test files**, since
fixtures differ on purpose.

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

23 tests, no dependencies. They build a synthetic wiki and repos in a temp dir, so they do not
depend on anyone's filesystem. Every check has both a fires-when-it-should and a
stays-quiet-when-it-should case, because a check that cannot be silenced correctly gets silenced
globally.

## What it does not do

- **It mostly enforces conventions rather than discovering violations of them.** `constant-drift`
  is the one exception. Everywhere else, a repo that diverges without writing a marker is
  invisible, and that is the honest ceiling on this design.
- `constant-drift` only sees UPPER_SNAKE names holding literal values. Drift inside a JSON
  structure, a function default, or a computed expression goes unnoticed.
- It does not check that a *number quoted in prose* still matches the code. The wiki saying "1500
  vs 1608" stays true-looking forever.
- It is a consistency checker, not a retrieval system. It will not find you the right page.
