#!/usr/bin/env python3
"""Regression checks for XSS-safe search/FAB rendering (build-index.py)."""
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
BUILD = ROOT / "build-index.py"
FIXTURE = ROOT / "tests" / "fixtures" / "search-xss-payload.json"


def extract_js_const(name: str) -> str:
    src = BUILD.read_text(encoding="utf-8")
    pat = rf"^{name} = \"\"\"(.*?)\"\"\""
    m = re.search(pat, src, re.S | re.M)
    if not m:
        raise AssertionError(f"{name} not found in build-index.py")
    return m.group(1)


class TestSearchSecuritySource(unittest.TestCase):
    def test_search_js_uses_safe_dom(self):
        js = extract_js_const("SEARCH_JS")
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("hits.map", js)
        self.assertIn("safeResultHref", js)
        self.assertIn("textContent", js)
        self.assertIn("appendResultCard", js)

    def test_fab_menu_uses_safe_dom(self):
        js = extract_js_const("JS")
        idx = js.find("getElementById('fabMenu')")
        self.assertGreater(idx, 0)
        fab = js[idx:]
        self.assertNotIn("menu.innerHTML", fab)
        self.assertIn("replaceChildren", fab)


class TestGeneratedOutput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(
            [sys.executable, str(BUILD)],
            check=True,
            cwd=ROOT,
            capture_output=True,
        )

    def test_search_html_reflects_safe_renderer(self):
        html = (ROOT / "search.html").read_text(encoding="utf-8")
        self.assertIn("safeResultHref", html)
        self.assertNotIn("hits.map", html)
        self.assertNotIn("results.innerHTML", html)

    def test_csp_meta_present(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("referrer", html)

    def test_all_generated_pages_safe_fab_menu(self):
        for name in (
            "index.html",
            "news.html",
            "events.html",
            "vreme.html",
            "search.html",
            "assistants.html",
        ):
            path = ROOT / name
            if not path.is_file():
                continue
            html = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "menu.innerHTML",
                html,
                msg="%s still uses menu.innerHTML" % name,
            )

    def test_xss_fixture_renders_as_text_not_markup(self):
        """Malicious titles in search.json must not become executable HTML in output JS."""
        self.assertTrue(FIXTURE.is_file(), "missing XSS fixture")
        payload = FIXTURE.read_text(encoding="utf-8")
        self.assertIn("<script>", payload)
        html = (ROOT / "search.html").read_text(encoding="utf-8")
        # Generator ships safe client renderer; user data never concatenated into HTML strings.
        self.assertIn("entry.t || ''", html)
        self.assertNotRegex(
            html,
            re.compile(r"innerHTML\s*=\s*hits\.map", re.I),
        )


if __name__ == "__main__":
    unittest.main()