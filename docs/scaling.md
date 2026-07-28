# Scaling past one curator

Everything in [why-a-curated-index.md](why-a-curated-index.md) works because I am one person with
an agent, over a corpus small enough that I have read all of it. The obvious question is what
happens with a thousand people and a hundred repos.

This page is the design. Parts of it I have built at a scale of one. The rest is reasoning, and I
have marked which is which, because a design nobody has run is worth less than one that has.

## What actually breaks

Not missing documents. **Semantic collision**: the same term carrying two definitions, both sides
confident, no visible disagreement. That is the failure mode from the biofix bug, and it gets
strictly worse with more writers, because every new actor is a new chance for someone to introduce
a second definition of a word that already has one.

Volume of documents is a retrieval problem. Volume of *authors* is a consistency problem. They are
not the same problem and they do not have the same fix.

## Two fixes that do not work

**Keyword detection.** It would have missed my flagship example outright. Both repos said "GDD",
the keyword matched perfectly, the definitions behind it diverged. Keyword search is blind to this
by construction, it matches vocabulary and the vocabulary was never wrong.

**A human review pipeline over proposed wiki edits.** This is the intuitive answer and it
relocates the bottleneck instead of removing it. A review queue over a thousand actors is a queue,
and knowledge-review queues reliably die, everyone has seen a wiki with four hundred pending
edits. Routing judgment to a human does not reduce the amount of judgment required.

The volume of things needing human judgment has to drop. Not get better dispatched.

## What does work: make canonical statements executable

The wiki's value is not its prose, it is its **canonical assertions**. "Pest thresholds are base
50 from January 1" is not really a paragraph. It is a claim that every repo computing degree-days
can be tested against.

So: the wiki holds the definitions, CI enforces them, and drift **fails a build instead of waiting
for a reviewer**. Humans only ever see the cases a test cannot express. Curation cost then stops
scaling with actor count, because most drift gets caught by machines that do not get tired and do
not have a backlog.

**Built (n=1):** a separate bug in the same module got pinned with a regression test in the repo
that had to honour it, so the old behaviour cannot silently come back. One canonical statement,
one test, one repo. That is the mechanism working at the smallest possible scale.

**Not built:** the general version, where assertions are declared once in the wiki and checked
across every repo automatically.

**And here is what happens without it.** The definition divergence above got a decided lane and a
convention page, and the wiki recorded it as resolved. The repo that has to honour it still
carries an open `DIVERGENCE:` note, because the code change is not written. Both statements are
true, about different things, and nothing anywhere reconciles them. A prose resolution is a claim
about the future; only a test makes it a claim about the present. I found this by hand, weeks
later, while checking numbers for the other page, which is precisely the detection latency this
whole design is meant to remove.

## The detection layer is a linter, not a search

This follows from the failure mode. If the problem is one term with two definitions, you are not
looking for documents, you are looking for **conflict**:

- the same named constant with different values in two repos
- a glossary term appearing alongside numbers that disagree across repos
- a wiki claim contradicted by a test downstream of it
- a canonical page with no test pinning it anywhere

Closer to type-checking than to retrieval. A type checker does not find you relevant code, it
finds you the place where two parts of a system disagree about what something is. That is the same
job.

This is also just the `lint` operation already in the schema, made **continuous and executable
rather than periodic and manual**. It is not a new subsystem bolted on the side, it is the
existing one moved from my discretion to a machine's.

## The wrinkle I have not solved

Cross-repo CI is genuinely harder than single-repo CI, and hand-waving it would be dishonest.

A test lives in a repo and runs in that repo's pipeline. An assertion that spans repos has no
natural home. The two shapes that seem workable:

1. **The wiki publishes.** Canonical assertions become a small versioned package, each repo
   depends on it, and each repo's own CI runs the checks that apply to it. Clean, but it makes the
   wiki a build dependency, and a knowledge layer that can break your build is a knowledge layer
   people will route around.
2. **Each repo fetches.** Repos pull the current assertions at CI time and check against them. No
   dependency edge, but now the checks are only as fresh as the fetch, and a repo can quietly stop
   fetching.

I have not run either at scale. The first looks right and the failure mode of the second looks
familiar in a bad way.

## The through-line

The rest of my work runs on one stance: keep the model out of anything that has to be right. The
classifier abstains rather than guess a species. The home agent routes on deterministic
keyword-match rather than model choice, and never computes a time itself.

The wiki has not had its own version of that yet. Today it *flags* `VERIFY:` and `DIVERGENCE:`,
and flagging is a judgment call, made by a model, about something that has to be right. Executable
lint is the wiki finally getting the same treatment as everything else: **the agent proposes, a
deterministic check decides.**

That is the argument for this direction, more than any scaling number. It is the same design being
applied to the one layer that was still running on trust.
