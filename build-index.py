#!/usr/bin/env python3
# build-index.py — генерира index.html + feed.xml за сайта с дайджестите.
# Дизайн: mobile-first, топла хартия (#FBF9F3), един тухлен акцент (#9C493D),
# лепкаво меню с хапчета + scrollspy, секции с фиксиран ред. Съдържанието се
# чете НА СТРАНИЦАТА: малките файлове без скриптове се вграждат директно,
# изданията (новини/дайджест) и файловете със скриптове се показват във
# вграден iframe с автоматична височина (same-origin измерване от родителя).
# Никой не отваря отделни HTML файлове — архивът се разгръща на място
# (data-src се зарежда при първо отваряне). Без външни зависимости.
# Пуска се от publish.ps1 на PC-то. Изход: index.html, feed.xml.
import html as htmlmod
import os
import re
import sys
from datetime import datetime

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://frashev.github.io/digest-site/"

WEEKDAYS_BG = ["понеделник", "вторник", "сряда", "четвъртък", "петък", "събота", "неделя"]
WEEKDAYS_SHORT = ["пон", "вто", "сря", "чет", "пет", "съб", "нед"]
MONTHS_BG = ["януари", "февруари", "март", "април", "май", "юни",
             "юли", "август", "септември", "октомври", "ноември", "декември"]

PART_LABEL = {"morning": "сутрин", "afternoon": "следобед", "evening": "вечер",
              "review": "обзор"}
PART_ORDER = {"morning": 0, "afternoon": 1, "evening": 2, "review": 3}
PART_EMOJI = {"morning": "🌅", "afternoon": "🌆", "evening": "🌙", "review": "📰"}

MIN_SIZE = 1024


def esc(s):
    return htmlmod.escape(s, quote=True)


def read_file(name):
    with open(os.path.join(SITE_DIR, name), encoding="utf-8", errors="replace") as f:
        return f.read()


def file_mtime(name):
    return os.path.getmtime(os.path.join(SITE_DIR, name))


def fmt_date(dt):
    return dt.strftime("%d.%m.%Y")


def weekday_bg(dt):
    return WEEKDAYS_BG[dt.weekday()]


def parse_news_name(name):
    m = re.match(r"novini-(\d{4})-(\d{2})-(\d{2})-(morning|afternoon|evening)\.html$", name)
    if m:
        y, mo, d, part = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        return {"name": name, "date": datetime(y, mo, d), "part": part, "label": None}
    m = re.match(r"novini-(\d{4})-(\d{2})-(\d{2})-(\d{2})\.html$", name)
    if m:
        y, mo, d1, d2 = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
        return {"name": name, "date": datetime(y, mo, d1), "part": "review",
                "label": "%02d–%02d.%02d.%d · обзор" % (d1, d2, mo, y)}
    return None


def parse_digest_name(name):
    m = re.match(r"digest-(\d{4})-(\d{2})-(\d{2})\.html$", name)
    if m:
        return {"name": name, "date": datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                "kind": "daily", "label": None}
    m = re.match(r"digest-week-(\d{4})-(\d{2})-(\d{2})\.html$", name)
    if m:
        return {"name": name, "date": datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                "kind": "weekly", "label": "седмичен списък"}
    m = re.match(r"events-(\d{4})-(\d{2})-(\d{2})-(\d{2})-evenings\.html$", name)
    if m:
        return {"name": name, "date": datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                "kind": "evenings",
                "label": "%s–%s.%s.%s · вечерни" % (m.group(3), m.group(4), m.group(2), m.group(1))}
    m = re.match(r"digest-tonight-(\d{4})-(\d{2})-(\d{2})\.html$", name)
    if m:
        return {"name": name, "date": datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                "kind": "tonight",
                "label": "Тази вечер · %s.%s.%s" % (m.group(3), m.group(2), m.group(1))}
    return None


def extract_h4_titles(html_text, limit=3):
    titles = []
    for t in re.findall(r"<h4[^>]*>(.*?)</h4>", html_text, re.S):
        t = re.sub(r"<[^>]+>", "", t)
        t = htmlmod.unescape(t).strip()
        t = re.sub(r"\s+", " ", t)
        if t:
            titles.append(t)
        if len(titles) >= limit:
            break
    return titles


def extract_first_headings(html_text, limit=3):
    titles = []
    for t in re.findall(r"<h[34][^>]*>(.*?)</h[34]>", html_text, re.S):
        t = re.sub(r"<[^>]+>", "", t)
        t = htmlmod.unescape(t).strip()
        t = re.sub(r"\s+", " ", t)
        if t:
            titles.append(t)
        if len(titles) >= limit:
            break
    return titles


def count_articles(html_text):
    return len(re.findall(r"<article[^>]*>", html_text))


def plain_text(html_text, limit=600):
    t = re.sub(r"<script.*?</script>", " ", html_text, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


def inline_body(name):
    """Връща тялото на малък файл без скриптове, без първия <h1> и без <style>."""
    text = read_file(name)
    m = re.search(r"<body>(.*?)</body>", text, re.S)
    body = m.group(1) if m else text
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    return body.strip()


def is_inlineable(name):
    text = read_file(name)
    return "<script" not in text and 'id="' not in text


def scan():
    names = [n for n in os.listdir(SITE_DIR)
             if n.endswith(".html") and n not in ("index.html",)
             and "test" not in n.lower() and not n.endswith("-share.html")
             and os.path.getsize(os.path.join(SITE_DIR, n)) >= 1]
    news, digests, singles = [], [], {}
    for name in sorted(names):
        pn = parse_news_name(name)
        if pn:
            news.append(pn)
            continue
        pd = parse_digest_name(name)
        if pd:
            digests.append(pd)
            continue
        singles[name] = name
    return news, digests, singles

CSS = """
:root{
  --bg:#FBF9F3; --surface:#FFFFFF; --surface-2:#F5F1E8; --surface-3:#F2EDE8;
  --ink:#2B2118; --ink-soft:#3D3226; --muted:#5F5E5C;
  --border:#E8E4DA; --border-strong:#DBD7CD;
  --accent:#9C493D; --accent-dark:#7A3B2B; --accent-soft:#FBEADD;
  --terra:#CE6246; --highlight:#F7DC1F; --highlight-soft:#FCF9E7;
  --sage:#5F7263; --focus:#1D4ED8;
  --r-sm:8px; --r-md:12px; --r-lg:16px; --r-xl:20px; --r-pill:999px;
  --shadow-card:0 1px 2px rgba(43,33,24,.05),0 8px 24px rgba(43,33,24,.06);
  --shadow-lift:0 2px 4px rgba(43,33,24,.06),0 16px 32px rgba(43,33,24,.10);
  --font-sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans",sans-serif;
  --font-serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;font-family:var(--font-sans);font-size:17px;line-height:1.6;background:var(--bg);color:var(--ink)}
h1,h2{font-family:var(--font-serif);color:var(--ink-soft)}
a{color:var(--accent);font-weight:600}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.skip-link{position:absolute;left:-999px;top:0;background:var(--ink);color:#fff;padding:10px 16px;border-radius:0 0 12px 0;z-index:100}
.skip-link:focus{left:0;color:#fff}
.container{max-width:1080px;margin:0 auto;padding:0 16px}
.site-header{position:sticky;top:0;z-index:50;background:rgba(251,249,243,.94);backdrop-filter:blur(8px);border-bottom:1px solid var(--border)}
.header-row{display:flex;align-items:center;gap:12px;padding:10px 0}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--ink);min-width:0}
.brand img{width:32px;height:32px;flex:none}
.brand-name{font-family:var(--font-serif);font-size:20px;font-weight:600;white-space:nowrap}
.brand-date{color:var(--muted);font-size:13px;white-space:nowrap}
.nav{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding:0 0 10px;-webkit-overflow-scrolling:touch}
.nav::-webkit-scrollbar{display:none}
.nav a{flex:none;padding:8px 14px;border-radius:var(--r-pill);color:var(--muted);text-decoration:none;font-size:15px;font-weight:500;min-height:36px;display:inline-flex;align-items:center}
.nav a[aria-current="true"]{background:var(--accent-soft);color:var(--ink);font-weight:600}
.searchbar{padding:14px 0 4px}
.searchbar input{width:100%;padding:12px 18px;border:1px solid var(--border-strong);border-radius:var(--r-pill);font-size:16px;font-family:var(--font-sans);background:var(--surface);color:var(--ink)}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.chip{border:1.5px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:var(--r-pill);padding:7px 14px;cursor:pointer;font-size:14px;font-weight:600;font-family:var(--font-sans);min-height:36px}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.count-line{color:var(--muted);font-size:13px;margin:8px 0 0;min-height:18px}
.hero{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-xl);box-shadow:var(--shadow-card);padding:24px;margin:24px 0 8px}
.hero .kicker{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
.hero h1{font-size:clamp(28px,6vw,40px);line-height:1.1;margin:8px 0 6px;letter-spacing:-.01em}
.hero h1 em{font-style:italic}
.hero .hl{background:linear-gradient(transparent 55%,var(--highlight) 55%,var(--highlight) 92%,transparent 92%);padding:0 2px}
.hero p.lede{color:var(--muted);margin:6px 0 16px}
.hero ul{margin:0 0 18px;padding-left:20px}
.hero li{margin:5px 0}
.btn-primary{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:12px 22px;border-radius:var(--r-pill);font-size:15px;font-weight:600}
.btn-primary:hover{background:var(--accent-dark)}
main section{padding:40px 0;border-top:1px solid var(--border);scroll-margin-top:84px}
main section h2{font-size:clamp(24px,3vw,30px);line-height:1.15;margin:0 0 4px}
.section-intro{color:var(--muted);margin:0 0 20px;font-size:15px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);box-shadow:var(--shadow-card);padding:20px}
.card h3{margin:0 0 6px;font-size:19px;line-height:1.3}
.card .meta{color:var(--muted);font-size:13px;margin:0 0 10px}
.card ul{margin:0 0 14px;padding-left:20px}
.card li{margin:4px 0;font-size:15px}
.card:hover{box-shadow:var(--shadow-lift)}
details.edition{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);box-shadow:var(--shadow-card);margin:0 0 12px;overflow:hidden}
details.edition summary{list-style:none;cursor:pointer;padding:14px 18px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;font-weight:600}
details.edition summary::-webkit-details-marker{display:none}
details.edition summary .chev{margin-left:auto;color:var(--muted);transition:transform 150ms ease}
details.edition[open ] summary .chev{transform:rotate(90deg)}
details.edition .ed-part{font-size:15px}
details.edition .ed-date{color:var(--muted);font-weight:500;font-size:14px}
details.edition .ed-meta{color:var(--muted);font-weight:500;font-size:14px}
.ed-body{border-top:1px solid var(--border)}
.ed-body iframe{width:100%;border:0;display:block;background:var(--surface);min-height:320px}
.frame-note{font-size:13px;color:var(--muted);margin:0 0 12px}
.frame-wrap{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);box-shadow:var(--shadow-card);overflow:hidden}
.frame-wrap iframe{width:100%;border:0;display:block;background:var(--surface);min-height:320px}
.archive-month{margin:0 0 12px}
.archive-month summary{cursor:pointer;font-weight:600;padding:12px 4px;font-size:16px}
.archive-month summary::-webkit-details-marker{display:none}
.inline-content .wrap{max-width:none;margin:0;padding:0}
.inline-content h2{font-size:20px;margin:0 0 10px}
.inline-content .day{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px 16px;margin:0 0 12px}
.inline-content .day h2{font-size:15px;margin:0 0 8px;color:var(--accent);font-family:var(--font-sans)}
.inline-content .item{margin:6px 0}
.inline-content .time{color:var(--muted);font-size:13px}
.inline-content .note{font-size:13px;color:var(--muted)}
.inline-content .check{background:var(--highlight-soft)}
.inline-content ul{margin:6px 0 0;padding-left:20px}
.inline-content li{margin:4px 0}
.inline-content table{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden}
.inline-content th,.inline-content td{text-align:left;padding:10px 12px;font-size:14px;border-bottom:1px solid var(--border);vertical-align:top}
.inline-content th{background:var(--surface-2);color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.inline-content tr:last-child td{border-bottom:none}
.inline-content .warn{color:var(--accent);font-weight:600}
.inline-content .dow{color:var(--muted);font-size:12px}
footer{border-top:1px solid var(--border);padding:28px 0 40px;color:var(--muted);font-size:14px}
footer a{font-weight:600}
.no-results{color:var(--muted);padding:20px 0}
@media (min-width:900px){
  main section{padding:64px 0}
  .hero{padding:32px}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{animation-duration:.01ms !important;transition-duration:.01ms !important}
}
"""

JS = """
// Scrollspy — активната секция в менюто
(function(){
  var links = document.querySelectorAll('.nav a[href^="#"]');
  var map = new Map();
  links.forEach(function(a){ map.set(a.getAttribute('href').slice(1), a); });
  var spy = new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if (!e.isIntersecting) return;
      links.forEach(function(a){ a.removeAttribute('aria-current'); });
      var link = map.get(e.target.id);
      if (link) link.setAttribute('aria-current', 'true');
    });
  }, { rootMargin: '-15% 0px -70% 0px' });
  document.querySelectorAll('main section[id]').forEach(function(s){ spy.observe(s); });
})();
// Търсене + филтри по вид
(function(){
  var q = document.getElementById('q');
  var countEl = document.getElementById('count');
  var noRes = document.getElementById('no-results');
  var activeKind = '';
  function apply(){
    var needle = (q.value || '').trim().toLowerCase();
    var visible = 0, total = 0;
    document.querySelectorAll('[data-search]').forEach(function(card){
      total++;
      var hitText = !needle || card.dataset.search.toLowerCase().indexOf(needle) !== -1;
      var hitKind = !activeKind || !card.dataset.kind || card.dataset.kind === activeKind;
      var hit = hitText && hitKind;
      card.hidden = !hit;
      if (hit) visible++;
    });
    document.querySelectorAll('main section').forEach(function(sec){
      var cards = sec.querySelectorAll('[data-search]');
      if (!cards.length) return;
      var anyVisible = false;
      cards.forEach(function(c){ if (!c.hidden) anyVisible = true; });
      sec.hidden = !anyVisible && (needle !== '' || activeKind !== '');
    });
    countEl.textContent = needle || activeKind ? ('Намерени: ' + visible + ' от ' + total) : '';
    noRes.hidden = visible > 0 || (!needle && !activeKind);
  }
  q.addEventListener('input', apply);
  document.querySelectorAll('.chip[data-kind]').forEach(function(chip){
    chip.addEventListener('click', function(){
      var kind = chip.dataset.kind;
      activeKind = (activeKind === kind) ? '' : kind;
      document.querySelectorAll('.chip[data-kind]').forEach(function(c){
        c.setAttribute('aria-pressed', c.dataset.kind === activeKind ? 'true' : 'false');
      });
      apply();
    });
  });
  document.getElementById('clear-filters').addEventListener('click', function(){
    q.value = ''; activeKind = '';
    document.querySelectorAll('.chip[data-kind]').forEach(function(c){ c.setAttribute('aria-pressed', 'false'); });
    apply();
  });
})();
// Зареждане на iframe при първо отваряне на <details>
(function(){
  function loadFrame(details){
    var f = details.querySelector('iframe[data-src]');
    if (f && !f.src) f.src = f.dataset.src;
  }
  document.querySelectorAll('details.edition').forEach(function(d){
    if (d.open) loadFrame(d);
    d.addEventListener('toggle', function(){ if (d.open) { loadFrame(d); setTimeout(fitIframes, 300); } });
  });
  document.querySelectorAll('[data-open-details]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var d = document.getElementById(btn.dataset.openDetails);
      if (d && !d.open) { d.open = true; loadFrame(d); }
    });
  });
})();
// Автоматична височина на вградените страници (same-origin измерване)
function fitIframes(){
  document.querySelectorAll('iframe[data-autosize]').forEach(function(f){
    try {
      if (!f.contentWindow || !f.contentDocument) return;
      var doc = f.contentDocument;
      var h = Math.max(doc.documentElement ? doc.documentElement.scrollHeight : 0,
                      doc.body ? doc.body.scrollHeight : 0);
      if (h > 100) f.style.height = (h + 8) + 'px';
    } catch (e) { /* cross-origin или още не е зареден — пропускаме */ }
  });
}
window.addEventListener('load', function(){ fitIframes(); setInterval(fitIframes, 900); });
window.addEventListener('resize', fitIframes);
"""


def news_card(item, html_text, open_by_default=False):
    count = count_articles(html_text)
    preview = extract_h4_titles(html_text, 3)
    label = PART_LABEL[item["part"]]
    emoji = PART_EMOJI[item["part"]]
    date_str = fmt_date(item["date"])
    weekday = weekday_bg(item["date"])
    date_html = esc(item["label"]) if item.get("label") else "%s, %s" % (date_str, weekday)
    search = "%s %s %s %s %s" % (date_str, weekday, label, item["part"],
                                 " ".join(preview))
    bullets = "".join("<li>%s</li>" % esc(t) for t in preview)
    open_attr = " open" if open_by_default else ""
    return (
        '<details class="edition" id="ed-%s" data-kind="%s" data-search="%s"%s>'
        '<summary><span class="ed-part">%s %s</span>'
        '<span class="ed-date">%s</span>'
        '<span class="ed-meta">%d новини</span><span class="chev">›</span></summary>'
        '<div class="ed-body"><iframe data-src="%s" data-autosize loading="lazy" '
        'title="Новини %s — %s"></iframe></div>'
        '</details>'
        % (esc(item["name"][:-5]), item["part"], esc(search), open_attr,
           emoji, label, date_html, count, esc(item["name"]),
           date_str, label)
    )


def news_preview_card(item, html_text):
    count = count_articles(html_text)
    preview = extract_h4_titles(html_text, 3)
    label = PART_LABEL[item["part"]]
    emoji = PART_EMOJI[item["part"]]
    date_str = fmt_date(item["date"])
    bullets = "".join("<li>%s</li>" % esc(t) for t in preview)
    search = "%s %s %s %s" % (date_str, label, item["part"], " ".join(preview))
    return (
        '<article class="card" data-kind="%s" data-search="%s">'
        '<h3>%s %s · %s</h3><p class="meta">%s · %d новини</p><ul>%s</ul>'
        '<a class="btn-primary" href="#ed-%s" data-open-details="ed-%s">Чети изданието ↓</a>'
        '</article>'
        % (item["part"], esc(search), emoji, label, date_str, weekday_bg(item["date"]),
           count, bullets, esc(item["name"][:-5]), esc(item["name"][:-5]))
    )


def digest_row(item, html_text):
    count = count_articles(html_text)
    preview = extract_first_headings(html_text, 3)
    if item["kind"] == "daily":
        title = "%s, %s" % (fmt_date(item["date"]), weekday_bg(item["date"]))
        search_extra = " ".join(preview)
        meta = "%d събития" % count
        m = re.search(r"(\d+) събития.*🆓 (\d+) безплатни.*🆕 (\d+) нови", html_text, re.S)
        if m:
            meta = "%s събития · 🆓 %s безплатни · 🆕 %s нови" % (m.group(1), m.group(2), m.group(3))
    elif item["kind"] == "weekly":
        title = "%s · %s" % (fmt_date(item["date"]), item["label"])
        search_extra = "седмичен списък " + " ".join(preview)
        meta = "%d събития" % count
    else:
        title = item["label"]
        search_extra = "вечерни " + " ".join(preview)
        meta = "%d събития" % count
    search = "%s %s" % (title, search_extra)
    return (
        '<details class="edition" data-kind="events" data-search="%s">'
        '<summary><span class="ed-part">🗓️ %s</span>'
        '<span class="ed-meta">%s</span><span class="chev">›</span></summary>'
        '<div class="ed-body"><iframe data-src="%s" data-autosize loading="lazy" '
        'title="Дайджест %s"></iframe></div></details>'
        % (esc(search), esc(title), esc(meta), esc(item["name"]), esc(title))
    )


def single_section(sec_id, title, intro, name):
    if is_inlineable(name):
        body = inline_body(name)
        search = plain_text(body, 600)
        return (
            '<section id="%s" aria-labelledby="%s-h"><div class="container">'
            '<h2 id="%s-h">%s</h2><p class="section-intro">%s</p>'
            '<div class="inline-content" data-kind="%s" data-search="%s">%s</div>'
            '</div></section>'
            % (sec_id, sec_id, sec_id, esc(title), esc(intro), sec_id, esc(search), body)
        )
    search = "%s %s" % (title, intro)
    return (
        '<section id="%s" aria-labelledby="%s-h"><div class="container">'
        '<h2 id="%s-h">%s</h2><p class="section-intro">%s</p>'
        '<div class="frame-wrap" data-kind="%s" data-search="%s"><iframe src="%s" data-autosize loading="lazy" '
        'title="%s"></iframe></div>'
        '</div></section>'
        % (sec_id, sec_id, sec_id, esc(title), esc(intro), sec_id, esc(search), esc(name), esc(title))
    )


def build_feed(news_items):
    from email.utils import formatdate
    items = []
    for item in sorted(news_items, key=lambda x: (x["date"], PART_ORDER[x["part"]]),
                       reverse=True)[:20]:
        count = count_articles(read_file(item["name"]))
        title = "Новини %s — %s" % (fmt_date(item["date"]), PART_LABEL[item["part"]])
        pub = formatdate(file_mtime(item["name"]), usegmt=True)
        items.append(
            "<item><title>%s</title><link>%s%s</link>"
            "<pubDate>%s</pubDate><description>%d новини</description></item>"
            % (esc(title), BASE_URL, esc(item["name"]), pub, count)
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        '<title>Моите дайджести — Новини</title>'
        '<link>%s</link>'
        '<description>Новини сутрин, следобед и вечер — автоматичен обзор</description>'
        '<language>bg</language>%s</channel></rss>'
        % (BASE_URL, "".join(items))
    )

def main():
    news, digests, singles = scan()
    news.sort(key=lambda x: (x["date"], PART_ORDER[x["part"]]))
    digests.sort(key=lambda x: x["date"], reverse=True)

    texts = {}
    for item in news:
        texts[item["name"]] = read_file(item["name"])
    for item in digests:
        texts[item["name"]] = read_file(item["name"])

    updated_ts = 0
    for name in list(texts) + list(singles):
        updated_ts = max(updated_ts, file_mtime(name))
    updated = datetime.fromtimestamp(updated_ts).strftime("%d.%m.%Y %H:%M")
    now = datetime.now()
    today_str = "%s, %d %s %d" % (WEEKDAYS_BG[now.weekday()], now.day,
                                  MONTHS_BG[now.month - 1], now.year)

    sections = []
    nav = []

    # ---- Новини: hero + днес + архив ----
    if news:
        latest = news[-1]
        latest_date = latest["date"]
        today_items = [i for i in news if i["date"] == latest_date]
        today_cards = "".join(news_preview_card(i, texts[i["name"]]) for i in today_items)
        today_details = "".join(
            news_card(i, texts[i["name"]], open_by_default=(i is latest))
            for i in today_items
        )
        older = [i for i in news if i["date"] != latest_date]
        months = {}
        for item in older:
            months.setdefault((item["date"].year, item["date"].month), []).append(item)
        archive_html = ""
        for (y, mo) in sorted(months, reverse=True):
            items = sorted(months[(y, mo)], key=lambda x: (x["date"], PART_ORDER[x["part"]]),
                           reverse=True)
            rows = "".join(news_card(i, texts[i["name"]]) for i in items)
            archive_html += (
                '<details class="archive-month"><summary>%s %d · %d издания</summary>%s</details>'
                % (MONTHS_BG[mo - 1], y, len(items), rows)
            )
        sections.append(
            '<section id="news" aria-labelledby="news-h"><div class="container">'
            '<h2 id="news-h">Новини</h2>'
            '<p class="section-intro">Сутрин, следобед и вечер — чети на място, без да отваряш отделни файлове.</p>'
            '<div class="grid">%s</div>%s'
            '<h3 style="margin:28px 0 12px;font-family:var(--font-serif);font-size:20px">Архив</h3>%s'
            '</div></section>' % (today_cards, today_details, archive_html)
        )
        nav.append(("news", "Новини"))

    # ---- Събития: последен дайджест + архив ----
    if digests:
        daily = [d for d in digests if d["kind"] == "daily"]
        latest_d = daily[0] if daily else digests[0]
        latest_text = texts[latest_d["name"]]
        count = count_articles(latest_text)
        meta = "%d събития" % count
        m = re.search(r"(\d+) събития.*🆓 (\d+) безплатни.*🆕 (\d+) нови", latest_text, re.S)
        if m:
            meta = "%s събития · 🆓 %s безплатни · 🆕 %s нови" % (m.group(1), m.group(2), m.group(3))
        rest = [d for d in digests if d is not latest_d]
        archive_html = "".join(digest_row(d, texts[d["name"]]) for d in rest)
        sections.append(
            '<section id="events" aria-labelledby="events-h"><div class="container">'
            '<h2 id="events-h">Събития — дневен дайджест</h2>'
            '<p class="section-intro">%s · %s</p>'
            '<p class="frame-note">Филтрите са вътре в дайджеста: търсене, дни и категории.</p>'
            '<div class="frame-wrap" data-kind="events" data-search="събития дневен дайджест %s %s"><iframe src="%s" data-autosize loading="lazy" '
            'title="Дайджест %s"></iframe></div>'
            '<h3 style="margin:28px 0 12px;font-family:var(--font-serif);font-size:20px">По-стари дайджести</h3>%s'
            '</div></section>'
            % (fmt_date(latest_d["date"]), meta, fmt_date(latest_d["date"]), meta,
               esc(latest_d["name"]), fmt_date(latest_d["date"]), archive_html)
        )
        nav.append(("events", "Събития"))

    # ---- Единични файлове (фиксиран ред) ----
    single_defs = [
        ("week", "Седмицата напред", "Какво предстои през седмицата — от календара и пощата.",
         "week-ahead.html"),
        ("weather", "Времето в София", "Прогноза за следващите дни.",
         "weather.html"),
        ("podari", "Подари Време", "Доброволчество с деца — посещения, обучения и информация.",
         "podari-vreme.html"),
        ("radar", "RADAR действия", "Какво следва от последните AI RADAR издания.",
         "radar-actions.html"),
        ("cars", "Коли", "Обяви за коли, които следя.",
         "cars-dashboard.html"),
        ("aiplan", "AI план", "Какво уча и какво следва.",
         "udemy-plan-2026-11-05.html"),
        ("subs", "Абонаменти и разходи", "Месечен одит на абонаментите.",
         "subscriptions.html"),
    ]
    scout_files = sorted(n for n in singles if n.startswith("scout-") and n.endswith(".html"))
    if scout_files:
        single_defs.append(("scout", "AI разузнаване", "Карти от седмичното разузнаване.",
                            scout_files[-1]))
    for sec_id, title, intro, name in single_defs:
        if name in singles:
            sections.append(single_section(sec_id, title, intro, name))
            nav.append((sec_id, title))

    nav_html = "".join(
        '<a href="#%s">%s</a>' % (sec_id, esc(label)) for sec_id, label in nav
    )
    hero_html = ""
    if news:
        hero_html = (
            '<div class="hero"><p class="kicker">Най-новото</p>'
            '<h1>Новини <span class="hl">%s, %s</span> — <em>%s</em></h1>'
            '<p class="lede">%d новини · %s</p><ul>%s</ul>'
            '<a class="btn-primary" href="#ed-%s" data-open-details="ed-%s">Чети изданието ↓</a></div>'
            % (fmt_date(news[-1]["date"]), weekday_bg(news[-1]["date"]),
               PART_LABEL[news[-1]["part"]],
               count_articles(texts[news[-1]["name"]]),
               PART_EMOJI[news[-1]["part"]],
               "".join("<li>%s</li>" % esc(t) for t in extract_h4_titles(texts[news[-1]["name"]], 3)),
               esc(news[-1]["name"][:-5]), esc(news[-1]["name"][:-5]))
        )

    page = (
        '<!DOCTYPE html>\n<html lang="bg">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>Моите дайджести — новини, събития и справки</title>\n'
        '<meta name="description" content="Новини, събития и справки — обновява се автоматично.">\n'
        '<meta name="theme-color" content="#FBF9F3">\n'
        '<link rel="icon" href="favicon.ico" sizes="any">\n'
        '<link rel="icon" href="favicon.svg" type="image/svg+xml">\n'
        '<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">\n'
        '<link rel="apple-touch-icon" href="apple-touch-icon.png">\n'
        '<link rel="manifest" href="site.webmanifest">\n'
        '<link rel="alternate" type="application/rss+xml" title="Моите дайджести — Новини" href="feed.xml">\n'
        '<style>' + CSS + '</style>\n</head>\n<body>\n'
        '<a class="skip-link" href="#main">Към съдържанието</a>\n'
        '<header class="site-header"><div class="container">'
        '<div class="header-row"><a class="brand" href="#top">'
        '<img src="favicon.svg" alt="" width="32" height="32">'
        '<span class="brand-name">Моите дайджести</span></a>'
        '<span class="brand-date">' + esc(today_str) + '</span></div>'
        '<nav class="nav" aria-label="Раздели">' + nav_html + '</nav>'
        '</div></header>\n'
        '<div class="container searchbar" role="search">'
        '<input id="q" type="search" placeholder="Търси в дайджестите…" aria-label="Търси в дайджестите">'
        '<div class="chips">'
        '<button class="chip" data-kind="" aria-pressed="true">Всички</button>'
        '<button class="chip" data-kind="morning" aria-pressed="false">🌅 Сутрин</button>'
        '<button class="chip" data-kind="afternoon" aria-pressed="false">🌆 Следобед</button>'
        '<button class="chip" data-kind="evening" aria-pressed="false">🌙 Вечер</button>'
        '<button class="chip" data-kind="events" aria-pressed="false">🗓️ Събития</button>'
        '<button class="chip" id="clear-filters">Изчисти филтрите</button>'
        '</div><p class="count-line" id="count" aria-live="polite"></p>'
        '<p class="no-results" id="no-results" hidden>Няма съвпадения — опитай с по-кратка дума.</p>'
        '</div>\n'
        '<main id="main"><div class="container" id="top">' + hero_html + '</div>'
        + "".join(sections) +
        '</main>\n'
        '<footer><div class="container">'
        '<p>Последно обновяване: ' + esc(updated) + ' · Обновява се автоматично на всеки час.</p>'
        '<p><a href="feed.xml">RSS емисия — новините</a> · <a href="#top">Нагоре ↑</a></p>'
        '</div></footer>\n'
        '<script>' + JS + '</script>\n</body>\n</html>\n'
    )
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(SITE_DIR, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(build_feed(news))

    counts = {
        "total": len(news) + len(digests) + len(singles),
        "news": len(news), "digest": len(digests),
        "podari": 1 if "podari-vreme.html" in singles else 0,
        "radar": 1 if "radar-actions.html" in singles else 0,
        "cars": 1 if "cars-dashboard.html" in singles else 0,
        "aiplan": 1 if "udemy-plan-2026-11-05.html" in singles else 0,
        "events": len([d for d in digests if d["kind"] == "evenings"]),
        "week": 1 if "week-ahead.html" in singles else 0,
        "weather": 1 if "weather.html" in singles else 0,
        "subs": 1 if "subscriptions.html" in singles else 0,
        "scout": len(scout_files),
        "other": len([n for n in singles if n not in (
            "podari-vreme.html", "radar-actions.html", "cars-dashboard.html",
            "udemy-plan-2026-11-05.html", "week-ahead.html", "weather.html",
            "subscriptions.html") and not n.startswith("scout-")]),
    }
    print("INDEX: total=%d news=%d digest=%d podari=%d radar=%d cars=%d aiplan=%d "
          "events=%d week=%d weather=%d subs=%d scout=%d other=%d updated=%s"
          % (counts["total"], counts["news"], counts["digest"], counts["podari"],
             counts["radar"], counts["cars"], counts["aiplan"], counts["events"],
             counts["week"], counts["weather"], counts["subs"], counts["scout"],
             counts["other"], updated))
    print("INDEX-SIZE: index.html=%d bytes feed.xml=%d bytes"
          % (len(page.encode("utf-8")),
             len(build_feed(news).encode("utf-8"))))


if __name__ == "__main__":
    main()
