"""Tests for wikilint. Stdlib unittest, no dependencies.

Run: python3 -m unittest discover -s lint -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import wikilint as wl


def build(tmp: Path, wiki_files: dict[str, str], repo_files: dict[str, str]):
    wiki = tmp / "demo-wiki"
    repo = tmp / "demo-repo"
    for rel, body in wiki_files.items():
        p = wiki / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    for rel, body in repo_files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    cfg = {
        "wiki": str(wiki),
        "index": "index.md",
        "repos": [{"name": "demo", "path": str(repo)}],
        "wiki_ref_patterns": [r"demo-wiki/(?:[\w.-]+/)*([\w.-]+)\.md"],
    }
    cfg_path = tmp / "wikilint.json"
    cfg_path.write_text(json.dumps(cfg))
    return cfg_path


def run(cfg_path: Path) -> list[wl.Finding]:
    cfg = wl.load_config(cfg_path)
    wiki = wl.Wiki(Path(cfg["wiki"]), cfg["index"], cfg.get("journal_pages"))
    repos = wl.Repos(cfg["repos"], cfg["wiki_ref_patterns"], cfg["repo_extensions"],
                     vocabulary=wiki.vocabulary())
    out = []
    out += wl.check_config(repos, cfg["repos"])
    out += wl.check_constant_drift(wiki, repos)
    out += wl.check_unfilled_placeholder(wiki)
    out += wl.check_broken_path(wiki, repos)
    out += wl.check_unresolved_downstream(wiki, repos)
    out += wl.check_unpinned_decision(wiki, repos, cfg["canonical_dirs"])
    out += wl.check_orphan_pages(wiki)
    out += wl.check_dangling_canonical(wiki, repos, cfg["canonical_dirs"])
    out += wl.check_broken_links(wiki)
    return out


class WikiLintTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def checks(self, findings, name):
        return [f for f in findings if f.check == name]

    def test_wiki_resolved_but_repo_still_open(self):
        """The flagship. This is the bug the linter exists for."""
        cfg = build(
            self.tmp,
            {
                "index.md": "- RESOLVED 2026-07-26: the units divergence. [[units]]\n",
                "entities/units.md": "# units\nBase 50 from Jan 1.\n",
            },
            {
                "calc.py": (
                    '"""DIVERGENCE (open, 2026-07-26): we accumulate from a different start.\n'
                    'Canonical: demo-wiki/entities/units.md\n"""\n'
                ),
            },
        )
        hits = self.checks(run(cfg), "unresolved-downstream")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].severity, "error")
        self.assertIn("units", hits[0].message)

    def test_no_finding_when_repo_marker_also_resolved(self):
        cfg = build(
            self.tmp,
            {
                "index.md": "- RESOLVED 2026-07-26: the units divergence. [[units]]\n",
                "entities/units.md": "# units\n",
            },
            {"calc.py": '"""DIVERGENCE RESOLVED 2026-07-26. demo-wiki/entities/units.md"""\n'},
        )
        self.assertEqual(self.checks(run(cfg), "unresolved-downstream"), [])

    def test_resolution_needs_a_date_or_colon(self):
        """'## Resolved' is a heading, not a declaration."""
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n", "entities/units.md": "# units\n## Resolved\nold stuff\n"},
            {"calc.py": '"""DIVERGENCE: open. demo-wiki/entities/units.md"""\n'},
        )
        self.assertEqual(self.checks(run(cfg), "unresolved-downstream"), [])

    def test_unpinned_decision_flags_prose_only_resolution(self):
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n", "entities/units.md": "# units\nRESOLVED 2026-07-26: base 50.\n"},
            {"calc.py": "# see demo-wiki/entities/units.md\n"},
        )
        hits = self.checks(run(cfg), "unpinned-decision")
        self.assertEqual(len(hits), 1)
        self.assertIn("units", hits[0].message)

    def test_unpinned_decision_satisfied_by_a_test_reference(self):
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n", "entities/units.md": "# units\nRESOLVED 2026-07-26: base 50.\n"},
            {"tests/test_units.py": "# pins demo-wiki/entities/units.md\ndef test_x(): pass\n"},
        )
        self.assertEqual(self.checks(run(cfg), "unpinned-decision"), [])

    def test_journal_never_resolves_itself(self):
        """A log entry about a resolution belongs to the page it links, not the log."""
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n", "log.md": "RESOLVED 2026-07-26: something.\n",
             "entities/units.md": "# units\n"},
            {"calc.py": "# demo-wiki/entities/units.md\n"},
        )
        self.assertEqual(self.checks(run(cfg), "unpinned-decision"), [])

    def test_link_syntax_in_code_span_is_not_a_link(self):
        cfg = build(
            self.tmp,
            {"index.md": "Cross-link with `[[page-name]]`, see [[units]]\n",
             "entities/units.md": "# units\n"},
            {},
        )
        broken = self.checks(run(cfg), "broken-link")
        self.assertEqual([b for b in broken if "page-name" in b.message], [])

    def test_broken_link_reported_for_real_missing_page(self):
        cfg = build(
            self.tmp,
            {"index.md": "[[units]] and [[not-written-yet]]\n", "entities/units.md": "# units\n"},
            {},
        )
        broken = self.checks(run(cfg), "broken-link")
        self.assertEqual(len(broken), 1)
        self.assertIn("not-written-yet", broken[0].message)

    def test_orphan_page_detected(self):
        cfg = build(
            self.tmp,
            {"index.md": "nothing linked\n", "entities/lonely.md": "# lonely\n"},
            {},
        )
        hits = self.checks(run(cfg), "orphan-page")
        self.assertEqual(len(hits), 1)
        self.assertIn("lonely", hits[0].message)

    def test_dangling_canonical_when_no_repo_cites_it(self):
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n", "entities/units.md": "# units\n"},
            {"calc.py": "x = 1\n"},
        )
        hits = self.checks(run(cfg), "dangling-canonical")
        self.assertEqual(len(hits), 1)
        self.assertIn("units", hits[0].message)

    # --- robustness checks, each drawn from a bug that actually happened ---

    def test_missing_repo_path_is_a_loud_error_not_a_silent_skip(self):
        """The worst failure available to a consistency checker is failing open.

        A typo'd path used to mean the repo was never scanned, every check found
        nothing, and the report read clean.
        """
        cfg_path = build(self.tmp, {"index.md": "[[units]]\n", "entities/units.md": "# units\n"},
                         {"calc.py": "x = 1\n"})
        cfg = json.loads(cfg_path.read_text())
        cfg["repos"].append({"name": "typo", "path": str(self.tmp / "does-not-exist")})
        cfg_path.write_text(json.dumps(cfg))

        hits = self.checks(run(cfg_path), "config-error")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].severity, "error")
        self.assertIn("NOT checked", hits[0].message)

    def test_all_repos_unreadable_is_an_error(self):
        cfg_path = build(self.tmp, {"index.md": "x\n"}, {})
        cfg = json.loads(cfg_path.read_text())
        cfg["repos"] = [{"name": "gone", "path": str(self.tmp / "nope")}]
        cfg_path.write_text(json.dumps(cfg))
        hits = self.checks(run(cfg_path), "config-error")
        self.assertEqual([h.severity for h in hits], ["error", "error"])

    def test_broken_path_when_the_wiki_cites_a_file_that_is_gone(self):
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n", "entities/units.md": "Implemented in `src/deleted.py`.\n"},
            {"src/present.py": "x = 1\n"},
        )
        hits = self.checks(run(cfg), "broken-path")
        self.assertEqual(len(hits), 1)
        self.assertIn("deleted.py", hits[0].message)

    def test_moved_path_when_the_filename_exists_elsewhere(self):
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n", "entities/units.md": "Implemented in `old/calc.py`.\n"},
            {"new/calc.py": "x = 1\n"},
        )
        hits = self.checks(run(cfg), "moved-path")
        self.assertEqual(len(hits), 1)
        self.assertIn("calc.py", hits[0].message)

    def test_existing_path_not_flagged_bare_or_repo_qualified(self):
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n",
             "entities/units.md": "See `src/present.py` and `demo/src/present.py`.\n"},
            {"src/present.py": "x = 1\n"},
        )
        found = run(cfg)
        self.assertEqual(self.checks(found, "broken-path"), [])
        self.assertEqual(self.checks(found, "moved-path"), [])

    def test_unfilled_placeholder_is_reported(self):
        """The Apache LICENSE shipped with its placeholder intact. Same shape."""
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n",
             "entities/units.md": "Copyright [yyyy] [name of copyright owner]\nOwner: your-org\n"},
            {"calc.py": "x = 1\n"},
        )
        hits = self.checks(run(cfg), "unfilled-placeholder")
        self.assertEqual(len(hits), 2)

    def _drift_cfg(self, wiki_body: str, a_body: str, b_body: str) -> Path:
        wiki, ra, rb = self.tmp / "demo-wiki", self.tmp / "ra", self.tmp / "rb"
        for p, body in [(wiki / "index.md", wiki_body), (ra / "a.py", a_body),
                        (rb / "b.py", b_body)]:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        cfg_path = self.tmp / "wikilint.json"
        cfg_path.write_text(json.dumps({
            "wiki": str(wiki), "index": "index.md",
            "repos": [{"name": "a", "path": str(ra)}, {"name": "b", "path": str(rb)}],
            "wiki_ref_patterns": [r"demo-wiki/(?:[\w.-]+/)*([\w.-]+)\.md"],
        }))
        return cfg_path

    def test_constant_drift_across_repos(self):
        """Discovers a divergence nobody annotated, which is the real upgrade."""
        cfg = self._drift_cfg("The canonical base is `GDD_BASE`.\n",
                              "GDD_BASE = 50\n", "GDD_BASE = 45\n")
        hits = self.checks(run(cfg), "constant-drift")
        self.assertEqual(len(hits), 1)
        self.assertIn("GDD_BASE", hits[0].message)
        self.assertIn("50", hits[0].where)
        self.assertIn("45", hits[0].where)

    def test_constant_agreement_is_not_flagged(self):
        cfg = self._drift_cfg("`GDD_BASE`\n", "GDD_BASE = 50\n", "GDD_BASE = 50\n")
        self.assertEqual(self.checks(run(cfg), "constant-drift"), [])

    def test_constant_not_named_by_the_wiki_is_ignored(self):
        """Scope comes from the wiki. Unmentioned constants are not its business."""
        cfg = self._drift_cfg("nothing named here\n", "SOME_OTHER = 1\n", "SOME_OTHER = 2\n")
        self.assertEqual(self.checks(run(cfg), "constant-drift"), [])

    def test_non_literal_values_are_not_compared(self):
        """Expressions may be equal in every way that matters; guessing makes noise."""
        cfg = self._drift_cfg("`GDD_BASE`\n",
                              'GDD_BASE = float(os.environ.get("X", "50"))\n',
                              'GDD_BASE = float(os.getenv("X", "50"))\n')
        self.assertEqual(self.checks(run(cfg), "constant-drift"), [])

    def test_json_is_scanned_by_default(self):
        """Vendored data files are the cross-repo artifact this tool exists for."""
        self.assertIn(".json", wl.DEFAULT_REPO_EXTS)

    def test_exit_code_is_nonzero_on_error(self):
        cfg = build(
            self.tmp,
            {"index.md": "- RESOLVED 2026-07-26: [[units]]\n", "entities/units.md": "# units\n"},
            {"calc.py": '"""DIVERGENCE (open): demo-wiki/entities/units.md"""\n'},
        )
        self.assertEqual(wl.main(["-c", str(cfg), "--json"]), 1)

    def test_exit_code_zero_on_a_clean_wiki(self):
        cfg = build(
            self.tmp,
            {"index.md": "[[units]]\n", "entities/units.md": "# units\n"},
            {"tests/test_units.py": "# demo-wiki/entities/units.md\n"},
        )
        self.assertEqual(wl.main(["-c", str(cfg), "--json"]), 0)


if __name__ == "__main__":
    unittest.main()
