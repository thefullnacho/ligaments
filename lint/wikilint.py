#!/usr/bin/env python3
"""wikilint: a conflict linter for an LLM-maintained cross-project wiki.

This is not a search tool. It looks for places where the wiki and the repos it
describes disagree, which is the failure mode that costs you at the boundary
between repos: one term, two definitions, both sides internally consistent.

Stdlib only. Exits non-zero when findings are at or above --fail-on, so it can
sit in CI. See lint/README.md for the checks and the config format.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

SEVERITIES = ["info", "warn", "error"]

# Markers. The wiki writes `VERIFY:` / `DIVERGENCE:`; a resolution is recorded
# as `RESOLVED <date>:`. Repos use the same vocabulary in comments/docstrings.
RE_VERIFY = re.compile(r"\bVERIFY:", re.I)
RE_DIVERGENCE = re.compile(r"\bDIVERGENCE\b", re.I)
RE_RESOLVED = re.compile(r"\bRESOLVED\b", re.I)
# A *declaration* of resolution, as opposed to the word appearing in a heading
# like "## Resolved". Requires a date or a colon, which is how the schema says
# to write one: "RESOLVED 2026-07-26: <what was decided>".
RE_RESOLUTION = re.compile(r"\bRESOLVED\b[^\n]{0,24}?(?:20\d{2}-\d{2}-\d{2}|:)", re.I)
RE_OPEN_HINT = re.compile(r"\(\s*open\b", re.I)
RE_WIKILINK = re.compile(r"\[\[([^\]|#]+)")
RE_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")

# UPPER_SNAKE identifiers, which is the low-noise shape for a named constant. The
# wiki's use of a name is what makes it worth checking, so this doubles as the
# vocabulary extractor.
RE_CONSTANT = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")
RE_ASSIGN = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?:const|let|var|final|static)?[ \t]*"
    r"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)[ \t]*(?::[^=\n]+)?=[ \t]*([^\n]+?)[ \t]*(?:[;,]|\#|//|$)",
    re.M)
# Only compare things that are unambiguously literal. An expression like
# os.environ.get(...) may be equal across repos in every way that matters, and
# guessing produces exactly the false positives that get a linter muted.
RE_LITERAL = re.compile(r"""-?\d+(?:\.\d+)?|"[^"]*"|'[^']*'|[Tt]rue|[Ff]alse|None|null""")
# Paths written in the wiki, e.g. `brain/pest_watch.py`. Requires a slash and a
# known extension so prose is not mistaken for a path.
RE_PATHLIKE = re.compile(
    r"\b((?:[\w.-]+/)+[\w.-]+\.(?:py|md|json|ya?ml|toml|ts|tsx|js|jsx|sh|sql|txt|cfg|ini))\b")
# Template placeholders that were never filled in. The Apache LICENSE shipping
# with "[yyyy] [name of copyright owner]" is the canonical example.
PLACEHOLDER_PATTERNS = [
    (re.compile(r"\[yyyy\]|\[name of copyright owner\]", re.I), "unfilled licence placeholder"),
    (re.compile(r"<(?:path/to|your-|constellation name|repo-one|repo-two)[^>\n]*>", re.I),
     "unfilled template placeholder"),
    (re.compile(r"\b(?:your-org|example\.com|CHANGEME|FIXME|XXX|TBD)\b"), "placeholder left in place"),
    (re.compile(r"~/path/to/"), "example path left in place"),
]

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist",
    "build", ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages",
}
# .json matters more than it looks: vendored data files are exactly the kind of
# cross-repo artifact this tool exists to track.
DEFAULT_REPO_EXTS = [".py", ".md", ".json", ".ts", ".tsx", ".js", ".jsx",
                     ".toml", ".yaml", ".yml"]


@dataclass
class Finding:
    check: str
    severity: str
    message: str
    where: str
    detail: str = ""

    def render(self) -> str:
        head = f"[{self.severity.upper():5}] {self.check}: {self.message}"
        body = f"\n         {self.where}"
        if self.detail:
            body += "\n         " + self.detail.replace("\n", "\n         ")
        return head + body


def walk(root: Path, exts: list[str]):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if any(fn.endswith(e) for e in exts):
                yield Path(dirpath) / fn


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


RE_FENCE = re.compile(r"```.*?```", re.S)
RE_CODESPAN = re.compile(r"`[^`\n]*`")


def strip_code(text: str) -> str:
    """Drop fenced blocks and inline code so documentation of the link syntax
    is not mistaken for a link."""
    return RE_CODESPAN.sub(" ", RE_FENCE.sub(" ", text))


def slug(page: str) -> str:
    """Normalise a wiki page reference to a bare slug: 'entities/x.md' -> 'x'."""
    return Path(page.strip()).stem.strip().lower()


class Wiki:
    """The wiki side: pages, links, and which topics are declared resolved."""

    def __init__(self, root: Path, index_name: str, journal_pages: list[str] | None = None):
        self.root = root
        self.index_name = index_name
        # Journals record other pages' resolutions. A resolution written here
        # belongs to whatever it links to, never to the journal itself.
        self.journals = {slug(j) for j in (journal_pages or [index_name, "log.md"])}
        self.pages: dict[str, Path] = {}
        self.text: dict[str, str] = {}
        for p in walk(root, [".md"]):
            s = slug(p.name)
            self.pages[s] = p
            self.text[s] = read(p)

    def rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.root))
        except ValueError:
            return str(p)

    def links_from(self, page: str) -> set[str]:
        # Strip code spans and fenced blocks first: a schema page that documents
        # the `[[link]]` syntax is talking about links, not making them.
        txt = strip_code(self.text.get(page, ""))
        return {slug(m) for m in RE_WIKILINK.findall(txt)}

    def all_links(self) -> set[str]:
        out: set[str] = set()
        for s in self.pages:
            out |= self.links_from(s)
        return out

    def resolved_topics(self) -> dict[str, list[tuple[str, int, str]]]:
        """Topics the wiki declares RESOLVED, keyed by slug.

        A resolution line names its topic either by [[link]] or by living on a
        page, so both the linked slugs and the host page count as resolved.
        """
        out: dict[str, list[tuple[str, int, str]]] = {}
        for s, txt in self.text.items():
            for i, line in enumerate(txt.splitlines(), 1):
                if not RE_RESOLUTION.search(line):
                    continue
                linked = {slug(m) for m in RE_WIKILINK.findall(line)}
                if s in self.journals:
                    targets = linked  # a journal never resolves itself
                else:
                    targets = linked or {s}
                for t in targets:
                    out.setdefault(t, []).append((s, i, line.strip()))
        return out

    def vocabulary(self) -> set[str]:
        """UPPER_SNAKE names the wiki mentions. The wiki naming a constant is what
        makes it canonical, and therefore what makes it worth comparing."""
        out: set[str] = set()
        for txt in self.text.values():
            out |= set(RE_CONSTANT.findall(txt))
        return out

    def markers(self, kind: re.Pattern) -> list[tuple[str, int, str]]:
        hits = []
        for s, txt in self.text.items():
            for i, line in enumerate(txt.splitlines(), 1):
                if kind.search(line) and not RE_RESOLVED.search(line):
                    hits.append((s, i, line.strip()))
        return hits


class Repos:
    """The repo side: open markers, and which wiki pages each file references."""

    def __init__(self, specs: list[dict], ref_patterns: list[str], exts: list[str],
                 vocabulary: set[str] | None = None):
        self.ref_res = [re.compile(p) for p in ref_patterns]
        # (repo, path, lineno, line, referenced_slugs, is_test)
        self.open_markers: list[tuple[str, Path, int, str, set[str], bool]] = []
        self.refs: dict[str, set[tuple[str, Path, bool]]] = {}
        # A configured path that does not exist is a config ERROR, never a silent
        # skip. Failing open is the worst available behaviour for a consistency
        # checker: every check "passes" and the report reads clean.
        self.missing: list[tuple[str, Path]] = []
        self.roots: dict[str, Path] = {}
        self.rel_paths: set[str] = set()           # "repo/rel/path" for every file seen
        self.basenames: dict[str, set[str]] = {}   # filename -> {"repo/rel/path", ...}
        # name -> {(repo, rel, literal)}, restricted to the wiki's own vocabulary
        self.assignments: dict[str, set[tuple[str, str, str]]] = {}
        vocab = vocabulary or set()

        for spec in specs:
            name = spec["name"]
            root = Path(os.path.expanduser(spec["path"])).resolve()
            if not root.is_dir():
                self.missing.append((name, root))
                continue
            self.roots[name] = root
            for f in walk(root, exts):
                rel = f.relative_to(root).as_posix()
                self.rel_paths.add(f"{name}/{rel}")
                self.basenames.setdefault(f.name, set()).add(f"{name}/{rel}")
                txt = read(f)
                if not txt:
                    continue
                is_test = "test" in f.name.lower() or "tests" in f.parts
                if vocab and not is_test:
                    for m in RE_ASSIGN.finditer(txt):
                        const, value = m.group(1), m.group(2).strip()
                        if const in vocab and RE_LITERAL.fullmatch(value):
                            self.assignments.setdefault(const, set()).add((name, rel, value))
                file_refs = self._refs_in(txt)
                for s in file_refs:
                    self.refs.setdefault(s, set()).add((name, f, is_test))
                lines = txt.splitlines()
                for i, line in enumerate(lines, 1):
                    if not (RE_DIVERGENCE.search(line) or RE_VERIFY.search(line)):
                        continue
                    if RE_RESOLVED.search(line):
                        continue
                    # Scope the reference to the marker's own block, falling back
                    # to the file, so a marker inherits the page it cites nearby.
                    window = "\n".join(lines[max(0, i - 4): i + 12])
                    near = self._refs_in(window) or file_refs
                    self.open_markers.append((name, f, i, line.strip(), near, is_test))

    def _refs_in(self, text: str) -> set[str]:
        out: set[str] = set()
        for r in self.ref_res:
            for m in r.finditer(text):
                out.add(slug(m.group(m.lastindex or 0)))
        return out


def check_config(repos: Repos, specs: list[dict]) -> list[Finding]:
    """Fail loud on a misconfigured repo path.

    Without this the tool fails OPEN: a typo in a path means the repo is never
    scanned, every check finds nothing, and the report is a clean bill of health
    for a repo nobody looked at. False assurance is worse than no assurance.
    """
    out = []
    for name, root in repos.missing:
        out.append(Finding(
            check="config-error", severity="error",
            message=f"configured repo '{name}' does not exist, so it was NOT checked",
            where=str(root),
            detail="Every other check silently passes for this repo. Fix the path or "
                   "remove the entry; do not leave it dangling.",
        ))
    if specs and not repos.roots:
        out.append(Finding(
            check="config-error", severity="error",
            message="no configured repo could be read, so nothing downstream was checked",
            where="wikilint.json",
            detail="A green run here means nothing at all.",
        ))
    return out


def check_broken_path(wiki: Wiki, repos: Repos) -> list[Finding]:
    """The wiki cites a repo file that no longer exists.

    The cardinal rule says link down to the repo rather than copying facts up.
    Links that rot turn that rule into a liability, and a rename is the most
    common way a wiki starts quietly lying.
    """
    if not repos.roots:
        return []
    out = []
    for page in sorted(wiki.pages):
        seen: set[str] = set()
        for m in RE_PATHLIKE.finditer(wiki.text.get(page, "")):
            p = m.group(1)
            if p in seen:
                continue
            seen.add(p)
            # A path may be written bare ("brain/x.py") or repo-qualified
            # ("hestia/brain/x.py"); accept either, and ignore URLs.
            if "://" in wiki.text.get(page, "")[max(0, m.start() - 8):m.start()]:
                continue
            qualified = {f"{r}/{p}" for r in repos.roots} | {p}
            if qualified & repos.rel_paths:
                continue
            elsewhere = repos.basenames.get(Path(p).name)
            if elsewhere:
                out.append(Finding(
                    check="moved-path", severity="info",
                    message=f"'{p}' is not there, but that filename exists elsewhere",
                    where=wiki.rel(wiki.pages[page]),
                    detail=f"found at: {', '.join(sorted(elsewhere)[:3])}. Probably a move the "
                           "wiki did not follow.",
                ))
            else:
                out.append(Finding(
                    check="broken-path", severity="warn",
                    message=f"'{p}' does not exist in any configured repo",
                    where=wiki.rel(wiki.pages[page]),
                    detail="Either the file is gone and this claim is stale, or the repo that "
                           "owns it is missing from the config.",
                ))
    return out


def check_unfilled_placeholder(wiki: Wiki) -> list[Finding]:
    """Template placeholders that shipped as if they were content."""
    out = []
    for page in sorted(wiki.pages):
        for i, line in enumerate(wiki.text.get(page, "").splitlines(), 1):
            for pat, why in PLACEHOLDER_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                out.append(Finding(
                    check="unfilled-placeholder", severity="warn",
                    message=f"{why}: {m.group(0)[:60]}",
                    where=f"{page}.md:{i}",
                    detail=line.strip()[:150],
                ))
                break
    return out


def check_constant_drift(wiki: Wiki, repos: Repos) -> list[Finding]:
    """The same named constant holding different values in different repos.

    This is the only check that DISCOVERS a divergence rather than enforcing an
    annotation someone already wrote. Scope comes from the wiki: a constant is
    worth comparing precisely because the wiki thought it worth naming.
    """
    out = []
    for const, sites in sorted(repos.assignments.items()):
        values = {v for _, _, v in sites}
        if len(values) < 2:
            continue
        where = "; ".join(f"{r}/{p} = {v}" for r, p, v in sorted(sites))
        out.append(Finding(
            check="constant-drift", severity="warn",
            message=f"'{const}' has {len(values)} different values across repos",
            where=where,
            detail="The wiki names this constant, so the repos are expected to agree. "
                   "If the difference is deliberate, say so on the canonical page.",
        ))
    return out


def check_unresolved_downstream(wiki: Wiki, repos: Repos) -> list[Finding]:
    """The flagship: the wiki says resolved, a repo still says open."""
    out = []
    resolved = wiki.resolved_topics()
    for repo, path, lineno, line, refs, _ in repos.open_markers:
        for s in refs & resolved.keys():
            src_page, src_line, src_text = resolved[s][0]
            out.append(Finding(
                check="unresolved-downstream",
                severity="error",
                message=f"wiki declares '{s}' resolved, but {repo} still carries an open marker",
                where=f"{path}:{lineno}",
                detail=(f"repo:  {line[:150]}\n"
                        f"wiki:  {src_page}.md:{src_line}  {src_text[:150]}\n"
                        "A prose resolution is a claim about the future. Pin it with a test "
                        "or reopen it."),
            ))
    return out


def check_unpinned_decision(wiki: Wiki, repos: Repos, dirs: list[str]) -> list[Finding]:
    """Resolved topics that no test anywhere references, so nothing holds them."""
    out = []
    for s in sorted(wiki.resolved_topics()):
        if s not in wiki.pages or s in wiki.journals:
            continue
        if not any(d in wiki.pages[s].parts for d in dirs):
            continue
        holders = repos.refs.get(s, set())
        if any(is_test for _, _, is_test in holders):
            continue
        where = wiki.rel(wiki.pages[s])
        nontest = sorted({n for n, _, t in holders if not t})
        out.append(Finding(
            check="unpinned-decision",
            severity="warn",
            message=f"'{s}' is declared resolved but no test references it",
            where=where,
            detail=(f"referenced by (non-test): {', '.join(nontest) or 'nothing'}\n"
                    "Only a test makes a resolution a claim about the present."),
        ))
    return out


def check_broken_links(wiki: Wiki) -> list[Finding]:
    out = []
    for s in sorted(wiki.pages):
        for target in sorted(wiki.links_from(s)):
            if target not in wiki.pages:
                out.append(Finding(
                    check="broken-link", severity="info",
                    message=f"[[{target}]] has no page yet",
                    where=wiki.rel(wiki.pages[s]),
                    detail="Intentional TODO markers are fine; this is a to-write list.",
                ))
    return out


def check_orphan_pages(wiki: Wiki) -> list[Finding]:
    idx = slug(wiki.index_name)
    linked = wiki.links_from(idx)
    out = []
    for s in sorted(wiki.pages):
        if s == idx or s in linked or s in wiki.journals:
            continue
        if s.lower() in {"readme", "claude", "agents", "schema", "license"}:
            continue
        out.append(Finding(
            check="orphan-page", severity="warn",
            message=f"'{s}' is not linked from {wiki.index_name}",
            where=wiki.rel(wiki.pages[s]),
            detail="Unindexed pages stop being read, then stop being true.",
        ))
    return out


def check_dangling_canonical(wiki: Wiki, repos: Repos, dirs: list[str]) -> list[Finding]:
    """Canonical pages no repo cites: either dead, or the repos never got the memo."""
    out = []
    for s, p in sorted(wiki.pages.items()):
        if not any(d in p.parts for d in dirs):
            continue
        if repos.refs.get(s):
            continue
        out.append(Finding(
            check="dangling-canonical", severity="info",
            message=f"no repo references canonical page '{s}'",
            where=wiki.rel(p),
            detail="Either the convention is dead, or the repos that should honour it never cite it.",
        ))
    return out


def check_stale_verify(wiki: Wiki, max_age_days: int, today: date) -> list[Finding]:
    out = []
    for page, lineno, line in wiki.markers(RE_VERIFY):
        m = RE_DATE.search(line)
        if not m:
            continue
        try:
            when = date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            continue
        age = (today - when).days
        if age > max_age_days:
            out.append(Finding(
                check="stale-verify", severity="warn",
                message=f"VERIFY open {age} days",
                where=f"{page}.md:{lineno}",
                detail=line[:150],
            ))
    return out


def load_config(path: Path) -> dict:
    cfg = json.loads(read(path))
    cfg.setdefault("index", "index.md")
    cfg.setdefault("repo_extensions", DEFAULT_REPO_EXTS)
    cfg.setdefault("canonical_dirs", ["entities"])
    cfg.setdefault("stale_verify_days", 90)
    cfg.setdefault("journal_pages", [cfg["index"], "log.md"])
    cfg.setdefault("repos", [])
    if "wiki_ref_patterns" not in cfg:
        wiki_dir = Path(os.path.expanduser(cfg["wiki"])).name
        cfg["wiki_ref_patterns"] = [rf"{re.escape(wiki_dir)}/(?:[\w.-]+/)*([\w.-]+)\.md"]
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Conflict linter for an LLM-maintained wiki.")
    ap.add_argument("-c", "--config", default="wikilint.json", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--fail-on", choices=SEVERITIES, default="error",
                    help="minimum severity that exits non-zero (default: error)")
    ap.add_argument("--only", help="comma-separated check names to run")
    args = ap.parse_args(argv)

    if not args.config.is_file():
        print(f"wikilint: no config at {args.config}", file=sys.stderr)
        return 2
    cfg = load_config(args.config)

    wiki_root = Path(os.path.expanduser(cfg["wiki"])).resolve()
    if not wiki_root.is_dir():
        print(f"wikilint: wiki not found at {wiki_root}", file=sys.stderr)
        return 2

    wiki = Wiki(wiki_root, cfg["index"], cfg.get("journal_pages"))
    repos = Repos(cfg["repos"], cfg["wiki_ref_patterns"], cfg["repo_extensions"],
                  vocabulary=wiki.vocabulary())

    findings: list[Finding] = []
    findings += check_config(repos, cfg["repos"])
    findings += check_constant_drift(wiki, repos)
    findings += check_unfilled_placeholder(wiki)
    findings += check_broken_path(wiki, repos)
    findings += check_unresolved_downstream(wiki, repos)
    findings += check_unpinned_decision(wiki, repos, cfg["canonical_dirs"])
    findings += check_stale_verify(wiki, cfg["stale_verify_days"], datetime.now().date())
    findings += check_orphan_pages(wiki)
    findings += check_dangling_canonical(wiki, repos, cfg["canonical_dirs"])
    findings += check_broken_links(wiki)

    if args.only:
        keep = {c.strip() for c in args.only.split(",")}
        findings = [f for f in findings if f.check in keep]

    findings.sort(key=lambda f: (-SEVERITIES.index(f.severity), f.check, f.where))

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=1))
    else:
        print(f"wikilint: {len(wiki.pages)} wiki pages, {len(cfg['repos'])} repos, "
              f"{len(repos.open_markers)} open markers downstream\n")
        for f in findings:
            print(f.render() + "\n")
        counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
        print(f"{len(findings)} finding(s): "
              + ", ".join(f"{counts[s]} {s}" for s in reversed(SEVERITIES)))

    floor = SEVERITIES.index(args.fail_on)
    return 1 if any(SEVERITIES.index(f.severity) >= floor for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
