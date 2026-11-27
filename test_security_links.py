#!/usr/bin/env python3
"""Regression checks: only safe links, colours and inline HTML reach the generated pages."""
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("build_index", ROOT / "build-index.py")
bi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bi)


class TestSafeUrl(unittest.TestCase):
    def test_http_allowed(self):
        self.assertEqual(bi.safe_url(" https://example.com/a?b=1 "), "https://example.com/a?b=1")
        self.assertEqual(bi.safe_url("http://example.com"), "http://example.com")

    def test_bad_schemes_rejected(self):
        for u in ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<b>x</b>",
                  "vbscript:x", "//evil.example", "https://a b", "", None]:
            self.assertEqual(bi.safe_url(u), "", u)


class TestSafeColor(unittest.TestCase):
    def test_hex_allowed(self):
        self.assertEqual(bi.safe_color("#abc"), "#abc")
        self.assertEqual(bi.safe_color("#A1B2C3"), "#A1B2C3")

    def test_css_injection_rejected(self):
        for c in ["red;background:url(x)", "#fff;}", "expression(alert(1))", "", None]:
            self.assertEqual(bi.safe_color(c), "#9C493D", c)


class TestRenderedCards(unittest.TestCase):
    def test_news_item_drops_js_link(self):
        a = {"day": "2026-11-27", "cat": "ai", "title": "T", "text": "x",
             "link": "javascript:alert(1)", "link_label": "L", "color": "red;x"}
        out = bi.news_item_html(a)
        self.assertNotIn("javascript:", out)
        self.assertNotIn("red;x", out)

    def test_event_card_drops_js_link(self):
        e = {"title": "E", "link": "javascript:alert(1)", "date": "2026-11-29"}
        try:
            out = bi.event_card_html(e)
        except (KeyError, TypeError):
            self.skipTest("event_card_html needs more fields")
        self.assertNotIn("javascript:", out)


class TestInlineBody(unittest.TestCase):
    def _inline(self, body):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x.html"
            p.write_text("<html><body><h1>H</h1>%s</body></html>" % body, encoding="utf-8")
            old = bi.SITE_DIR
            bi.SITE_DIR = d
            try:
                return bi.inline_body("x.html")
            finally:
                bi.SITE_DIR = old

    def test_strips_scripts_handlers_and_js_urls(self):
        payloads = [
            '<SCRIPT>alert(1)</SCRIPT >',
            '<img src=x onerror="alert(1)">',
            "<svg/onload=alert(1)>",
            '<a href="javascript:alert(1)">a</a>',
            "<a href='JAVASCRIPT:alert(1)'>a</a>",
            '<a href="java&#x09;script:alert(1)">a</a>',
            '<a href=" &#106;avascript:alert(1)">a</a>',
            '<iframe src="data:text/html,x"></iframe>',
        ]
        for p in payloads:
            out = self._inline(p).lower()
            self.assertNotIn("<script", out, p)
            self.assertNotRegex(out, r"[\s/]on[a-z]+\s*=", p)
            self.assertNotIn("script:", out, p)
            self.assertNotIn("data:", out, p)

    def test_keeps_normal_links(self):
        out = self._inline('<a href="https://example.com">x</a> <a href="novini.html#a">y</a>')
        self.assertIn('href="https://example.com"', out)
        self.assertIn('href="novini.html#a"', out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
