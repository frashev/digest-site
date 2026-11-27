#!/usr/bin/env python3
"""Regression checks: only safe links, colours and inline HTML reach the generated pages."""
import importlib.util
from html.parser import HTMLParser
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("build_index", ROOT / "build-index.py")
bi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bi)


class _Attrs(HTMLParser):
    """Независима проверка: парсва като браузър и събира тагове и атрибути."""
    def __init__(self):
        super().__init__()
        self.tags, self.attrs = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend((k.lower(), (v or "")) for k, v in attrs)


def parse(html_text):
    a = _Attrs()
    a.feed(html_text)
    a.close()
    return a


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
        out = bi.event_card_html(e)
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
            '<img src="x"onerror="alert(1)">',
            "<img src='x'onerror=alert(1)>",
            '<img alt=">" onerror="alert(1)">',
            "<svg/onload=alert(1)>",
            '<a href="javascript:alert(1)">a</a>',
            "<a href=JAVASCRIPT:alert(1)>a</a>",
            "<a href='JAVASCRIPT:alert(1)'>a</a>",
            '<a href="java&#x09;script:alert(1)">a</a>',
            '<a href=" &#106;avascript:alert(1)">a</a>',
            '<iframe src="data:text/html,x"></iframe>',
            '<iframe srcdoc="&lt;script&gt;alert(1)&lt;/script&gt;"></iframe>',
            '<div srcdoc="x">d</div>',
            '<style>body{background:url(javascript:x)}</style>',
            '<base href="https://evil.example/"><meta http-equiv="refresh" content="0;url=x">',
            '<img src="data:image/svg+xml,<svg onload=alert(1)>">',
            '<scr<meta>ipt>alert(1)</scr<meta>ipt>',
            '<ifr<base>ame src="javascript:alert(1)"></ifr<base>ame>',
            '<sty<link>le>x</sty<link>le>',
            '<img src=x onerror=alert(1) a=b">',
            '<img src=x onerror=alert(1) x=<>',
            '<img src=x onerror=alert(1) a=b<c>',
            '<iframe src=x <b>>',
            '<img src=x title="a>b" onerror=alert(1) x=y\'>',
            "<img src=x t='a>b' onerror=alert(1) x=y\">",
            '<!--><img src=x onerror=alert(1)>-->',
            '<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>',
            '<svg><animate attributeName=href values=javascript:alert(1)></animate><set attributeName=href to=javascript:x /></svg>',
        ]
        bad_tags = {"script", "style", "iframe", "object", "embed", "base", "meta", "link", "animate", "set"}
        for p in payloads:
            out = self._inline(p)
            got = parse(out)
            self.assertFalse(bad_tags & set(got.tags), (p, out))
            for k, v in got.attrs:
                self.assertFalse(k.startswith("on") or k == "srcdoc", (p, out))
                if k in ("href", "src"):
                    plain = "".join(ch for ch in v if ord(ch) > 32).lower()
                    self.assertFalse(plain.startswith(("javascript:", "vbscript:", "data:text", "data:image/svg")), (p, out))

    def test_keeps_safe_schemes(self):
        out = self._inline('<a href="tel:+359888">t</a> <a href="mailto:a@b.c">m</a> '
                           '<img src="data:image/png;base64,iVBORw0KGgo=" alt="online now">')
        self.assertIn('href="tel:+359888"', out)
        self.assertIn('href="mailto:a@b.c"', out)
        self.assertIn('src="data:image/png;base64,iVBORw0KGgo="', out)
        self.assertIn('alt="online now"', out)

    def test_unquoted_url_and_self_closing(self):
        out = self._inline('<a href=http://x.com/>x</a><svg><path d="M0 0"/></svg>')
        self.assertIn('href="http://x.com/">', out)
        self.assertIn('<path d="M0 0"/>', out)

    def test_keeps_normal_links(self):
        out = self._inline('<a href="https://example.com">x</a> <a href="novini.html#a">y</a>')
        self.assertIn('href="https://example.com"', out)
        self.assertIn('href="novini.html#a"', out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
