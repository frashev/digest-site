#!/usr/bin/env python3
# build-index.py — генерира МНОГОСТРАНИЧЕН сайт с дайджестите.
# Дизайн: mobile-first, топла хартия (#FBF9F3), един тухлен акцент (#9C493D),
# лепкаво меню с къси етикети (активната страница е маркирана, менюто се
# скролва до нея, fade маска показва, че има още). Всяка страница е отделна:
# index (начало), news (новини), events (събития), week, vreme, podari,
# radar, cars, aiplan, subs, scout (ако има), search (глобално търсене).
# Съдържанието се чете НА СТРАНИЦАТА: малките файлове без скриптове се
# вграждат директно, изданията (новини/дайджест) и файловете със скриптове
# се показват във вграден iframe с автоматична височина — височината се мери
# по долния ръб на последния видим елемент (не по scrollHeight, за да няма
# празна ивица под съдържанието). Архивът се разгръща на място (data-src се
# зарежда при първо отваряне). Глобалното търсене чете search.json.
# Без външни зависимости. Пуска се от publish.ps1 на PC-то.
# Изход: index.html, news.html, events.html, week.html, vreme.html,
# podari.html, radar.html, cars.html, aiplan.html, subs.html, scout.html,
# search.html, search.json, feed.xml.
import html as htmlmod
import json
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

# Страниците, които самият генератор създава — НЕ са съдържание и не се
# взимат предвид при сканирането (иначе следващото пускане ще ги вземе
# за единични файлове).
GENERATED = ("index.html", "news.html", "events.html", "week.html", "vreme.html",
             "podari.html", "radar.html", "cars.html", "aiplan.html", "subs.html",
             "scout.html", "search.html")

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


def parse_other_event(name, html_text):
    """Еднократен файл със събития (не пасва на горните шаблони): заглавие
    от <title>, дата от името, ако има такава."""
    m = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    title = htmlmod.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip()) if m else name
    dm = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    date = datetime(int(dm.group(1)), int(dm.group(2)), int(dm.group(3))) if dm else None
    return {"name": name, "title": title, "date": date}


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
             if n.endswith(".html") and n not in GENERATED
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
.nav{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding:0 0 10px;-webkit-overflow-scrolling:touch;
  -webkit-mask-image:linear-gradient(90deg,#000 88%,transparent 100%);
  mask-image:linear-gradient(90deg,#000 88%,transparent 100%)}
.nav::-webkit-scrollbar{display:none}
.nav a{flex:none;padding:8px 14px;border-radius:var(--r-pill);color:var(--muted);text-decoration:none;font-size:15px;font-weight:500;min-height:36px;display:inline-flex;align-items:center}
.nav a[aria-current="page"]{background:var(--accent-soft);color:var(--ink);font-weight:600}
.page-hero{background:linear-gradient(160deg,#FFF6EC 0%,#FFFFFF 60%);border:1px solid var(--border);border-radius:var(--r-xl);box-shadow:var(--shadow-card);padding:24px;margin:24px 0 8px}
.page-hero .kicker{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
.page-hero h1{font-size:clamp(26px,5vw,34px);line-height:1.15;margin:8px 0 6px;letter-spacing:-.01em}
.page-hero p.lede{color:var(--muted);margin:6px 0 0}
.hero{background:linear-gradient(160deg,#FFF6EC 0%,#FFFFFF 60%);border:1px solid var(--border);border-radius:var(--r-xl);box-shadow:var(--shadow-card);padding:24px;margin:24px 0 8px}
.hero .kicker{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
.hero h1{font-size:clamp(28px,6vw,40px);line-height:1.1;margin:8px 0 6px;letter-spacing:-.01em}
.hero h1 em{font-style:italic}
.hero .hl{background:linear-gradient(transparent 55%,var(--highlight) 55%,var(--highlight) 92%,transparent 92%);padding:0 2px}
.hero p.lede{color:var(--muted);margin:6px 0 16px}
.hero ul{margin:0 0 18px;padding-left:20px}
.hero li{margin:5px 0}
.btn-primary{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:12px 22px;border-radius:var(--r-pill);font-size:15px;font-weight:600}
.btn-primary:hover{background:var(--accent-dark)}
.btn-ghost{display:inline-block;background:var(--surface);color:var(--accent);border:1.5px solid var(--accent);text-decoration:none;padding:10px 20px;border-radius:var(--r-pill);font-size:15px;font-weight:600}
main section{padding:32px 0 8px;scroll-margin-top:84px}
main section h2{font-size:clamp(24px,3vw,30px);line-height:1.15;margin:0 0 4px}
.section-intro{color:var(--muted);margin:0 0 20px;font-size:15px}
.section-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.section-head a{font-size:14px;white-space:nowrap}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);box-shadow:var(--shadow-card);padding:20px}
.card h3{margin:0 0 6px;font-size:19px;line-height:1.3}
.card .meta{color:var(--muted);font-size:13px;margin:0 0 10px}
.card ul{margin:0 0 14px;padding-left:20px}
.card li{margin:4px 0;font-size:15px}
.card:hover{box-shadow:var(--shadow-lift)}
.card .icon{font-size:26px}
.searchbar{padding:14px 0 4px}
.searchbar input{width:100%;padding:12px 18px;border:1px solid var(--border-strong);border-radius:var(--r-pill);font-size:16px;font-family:var(--font-sans);background:var(--surface);color:var(--ink)}
.count-line{color:var(--muted);font-size:13px;margin:8px 0 0;min-height:18px}
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
.result-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);box-shadow:var(--shadow-card);padding:16px 18px;margin:0 0 12px}
.result-card h3{margin:0 0 4px;font-size:17px}
.result-card .meta{color:var(--muted);font-size:13px;margin:0 0 6px}
.result-card p{margin:0;font-size:14px;color:var(--ink-soft)}
footer{border-top:1px solid var(--border);padding:28px 0 40px;color:var(--muted);font-size:14px;margin-top:32px}
footer a{font-weight:600}
footer .foot-nav{display:flex;flex-wrap:wrap;gap:4px 16px;margin:0 0 12px}
.no-results{color:var(--muted);padding:20px 0}
@media (min-width:900px){
  main section{padding:48px 0 8px}
  .hero,.page-hero{padding:32px}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{animation-duration:.01ms !important;transition-duration:.01ms !important}
}
"""

JS = """
// Менюто се скролва до активната страница
(function(){
  var cur = document.querySelector('.nav a[aria-current="page"]');
  if (cur) cur.scrollIntoView({inline:'center', block:'nearest'});
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
// Дълбок линк към издание/дайджест: отваря го при зареждане
(function(){
  var h = location.hash && location.hash.slice(1);
  if (!h) return;
  var el = document.getElementById(h);
  if (el && el.tagName === 'DETAILS') {
    el.open = true;
    var f = el.querySelector('iframe[data-src]');
    if (f && !f.src) f.src = f.dataset.src;
    setTimeout(function(){ el.scrollIntoView({block:'start'}); fitIframes(); }, 350);
  }
})();
// Търсене на страницата (новини/събития): филтрира картите по data-search
(function(){
  var q = document.getElementById('q');
  if (!q) return;
  var countEl = document.getElementById('count');
  var noRes = document.getElementById('no-results');
  function apply(){
    var needle = (q.value || '').trim().toLowerCase();
    var visible = 0, total = 0;
    document.querySelectorAll('[data-search]').forEach(function(card){
      total++;
      var hit = !needle || card.dataset.search.toLowerCase().indexOf(needle) !== -1;
      card.hidden = !hit;
      if (hit) visible++;
    });
    document.querySelectorAll('.archive-month').forEach(function(m){
      var anyVisible = false;
      m.querySelectorAll('[data-search]').forEach(function(c){ if (!c.hidden) anyVisible = true; });
      m.hidden = !anyVisible && needle !== '';
    });
    if (countEl) countEl.textContent = needle ? ('Намерени: ' + visible + ' от ' + total) : '';
    if (noRes) noRes.hidden = visible > 0 || !needle;
  }
  q.addEventListener('input', apply);
})();
// Автоматична височина на вградените страници: долният ръб на последния
// видим елемент в тялото (не scrollHeight — той брои и празното отдолу)
function fitIframes(){
  document.querySelectorAll('iframe[data-autosize]').forEach(function(f){
    try {
      if (!f.contentWindow || !f.contentDocument || !f.contentDocument.body) return;
      var doc = f.contentDocument, view = doc.defaultView, best = 0;
      var kids = doc.body.children;
      for (var i = 0; i < kids.length; i++) {
        var el = kids[i];
        if (view.getComputedStyle(el).display === 'none') continue;
        var r = el.getBoundingClientRect();
        if (!r.height && !r.width) continue;
        var bottom = r.top + view.scrollY + r.height;
        if (bottom > best) best = bottom;
      }
      var h = best > 100 ? best : doc.body.scrollHeight;
      if (h > 100) f.style.height = (h + 8) + 'px';
    } catch (e) { /* cross-origin или още не е зареден — пропускаме */ }
  });
}
window.addEventListener('load', function(){ fitIframes(); setInterval(fitIframes, 900); });
window.addEventListener('resize', fitIframes);
"""

SEARCH_JS = """
(function(){
  var q = document.getElementById('q');
  var results = document.getElementById('results');
  var countEl = document.getElementById('count');
  var data = null;
  function render(needle){
    needle = (needle || '').trim().toLowerCase();
    if (!data) { results.innerHTML = '<p class="no-results">Зареждам индекса…</p>'; return; }
    if (!needle) {
      results.innerHTML = '<p class="no-results">Напиши дума — търси в изданията, събитията и седмицата.</p>';
      countEl.textContent = '';
      return;
    }
    var hits = data.filter(function(e){
      return (e.t + ' ' + e.s + ' ' + e.k).toLowerCase().indexOf(needle) !== -1;
    }).slice(0, 40);
    countEl.textContent = 'Намерени: ' + hits.length;
    if (!hits.length) {
      results.innerHTML = '<p class="no-results">Няма съвпадения — опитай с по-кратка дума.</p>';
      return;
    }
    results.innerHTML = hits.map(function(e){
      return '<article class="result-card"><h3><a href="' + e.u + '">' + e.t + '</a></h3>'
        + '<p class="meta">' + e.k + (e.d ? ' · ' + e.d : '') + '</p>'
        + (e.s ? '<p>' + e.s + '</p>' : '') + '</article>';
    }).join('');
  }
  fetch('search.json').then(function(r){ return r.json(); }).then(function(j){
    data = j; render(q.value);
  }).catch(function(){
    results.innerHTML = '<p class="no-results">Индексът не се зареди — опитай отново след малко.</p>';
  });
  q.addEventListener('input', function(){ render(q.value); });
  var params = new URLSearchParams(location.search);
  if (params.get('q')) { q.value = params.get('q'); }
  render(q.value);
})();
"""


def news_slug(item):
    return item["name"][:-5]


def digest_slug(item):
    return item["name"][:-5]


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
    open_attr = " open" if open_by_default else ""
    return (
        '<details class="edition" id="ed-%s" data-kind="%s" data-search="%s"%s>'
        '<summary><span class="ed-part">%s %s</span>'
        '<span class="ed-date">%s</span>'
        '<span class="ed-meta">%d новини</span><span class="chev">›</span></summary>'
        '<div class="ed-body"><iframe data-src="%s" data-autosize loading="lazy" '
        'title="Новини %s — %s"></iframe></div>'
        '</details>'
        % (esc(news_slug(item)), item["part"], esc(search), open_attr,
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
        '<a class="btn-primary" href="news.html#ed-%s">Чети изданието ↓</a>'
        '</article>'
        % (item["part"], esc(search), emoji, label, date_str, weekday_bg(item["date"]),
           count, bullets, esc(news_slug(item)))
    )


def digest_meta(html_text):
    count = count_articles(html_text)
    meta = "%d събития" % count
    m = re.search(r"(\d+) събития.*🆓 (\d+) безплатни.*🆕 (\d+) нови", html_text, re.S)
    if m:
        meta = "%s събития · 🆓 %s безплатни · 🆕 %s нови" % (m.group(1), m.group(2), m.group(3))
    return meta


def digest_row(item, html_text, lazy=True):
    preview = extract_first_headings(html_text, 3)
    if item["kind"] == "daily":
        title = "%s, %s" % (fmt_date(item["date"]), weekday_bg(item["date"]))
        search_extra = " ".join(preview)
    elif item["kind"] == "weekly":
        title = "%s · %s" % (fmt_date(item["date"]), item["label"])
        search_extra = "седмичен списък " + " ".join(preview)
    else:
        title = item["label"]
        search_extra = "вечерни " + " ".join(preview)
    meta = digest_meta(html_text)
    search = "%s %s" % (title, search_extra)
    if lazy:
        frame = ('<iframe data-src="%s" data-autosize loading="lazy" '
                 'title="Дайджест %s"></iframe>' % (esc(item["name"]), esc(title)))
    else:
        frame = ('<iframe src="%s" data-autosize loading="lazy" '
                 'title="Дайджест %s"></iframe>' % (esc(item["name"]), esc(title)))
    return (
        '<details class="edition" id="dg-%s" data-kind="events" data-search="%s">'
        '<summary><span class="ed-part">🗓️ %s</span>'
        '<span class="ed-meta">%s</span><span class="chev">›</span></summary>'
        '<div class="ed-body">%s</div></details>'
        % (esc(digest_slug(item)), esc(search), esc(title), esc(meta), frame)
    )


def other_event_row(item, html_text):
    count = count_articles(html_text)
    title = item["title"]
    date_str = fmt_date(item["date"]) if item["date"] else ""
    search = "%s %s" % (title, date_str)
    return (
        '<details class="edition" data-kind="events" data-search="%s">'
        '<summary><span class="ed-part">🗓️ %s</span>'
        '<span class="ed-meta">%s · %d събития</span><span class="chev">›</span></summary>'
        '<div class="ed-body"><iframe data-src="%s" data-autosize loading="lazy" '
        'title="%s"></iframe></div></details>'
        % (esc(search), esc(title), esc(date_str), count, esc(item["name"]), esc(title))
    )


def single_body(name):
    """Тяло за страница на единичен файл: вградено или iframe."""
    if is_inlineable(name):
        body = inline_body(name)
        return '<div class="inline-content">%s</div>' % body
    return (
        '<div class="frame-wrap"><iframe src="%s" data-autosize loading="lazy" '
        'title="Съдържание"></iframe></div>' % esc(name)
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

    # Единични файлове (фиксиран ред) + еднократни файлове със събития
    single_defs = [
        ("week", "Седмицата", "Седмицата напред", "Какво предстои през седмицата — от календара и пощата.",
         "week-ahead.html", "📅"),
        ("vreme", "Времето", "Времето в София", "Прогноза за следващите дни.",
         "weather.html", "🌤️"),
        ("podari", "Подари Време", "Подари Време", "Доброволчество с деца — посещения, обучения и информация.",
         "podari-vreme.html", "❤️"),
        ("radar", "RADAR", "RADAR действия", "Какво следва от последните AI RADAR издания.",
         "radar-actions.html", "📡"),
        ("cars", "Коли", "Коли", "Обяви за коли, които следя.",
         "cars-dashboard.html", "🚗"),
        ("aiplan", "AI план", "AI план", "Какво уча и какво следва.",
         "udemy-plan-2026-11-05.html", "🤖"),
        ("subs", "Абонаменти", "Абонаменти", "Месечен одит на абонаментите.",
         "subscriptions.html", "💳"),
    ]
    scout_files = sorted(n for n in singles if n.startswith("scout-") and n.endswith(".html"))
    if scout_files:
        single_defs.append(("scout", "AI разузнаване", "AI разузнаване",
                            "Карти от седмичното разузнаване.", scout_files[-1], "🔭"))
    known_singles = {d[4] for d in single_defs}
    other_events = []
    for name in sorted(singles):
        if name in known_singles or name.startswith("scout-"):
            continue
        other_events.append(parse_other_event(name, read_file(name)))

    pages = [("index", "Начало", "index.html"),
             ("news", "Новини", "news.html"),
             ("events", "Събития", "events.html")]
    for sec_id, nav_label, _t, _i, _f, _e in single_defs:
        pages.append((sec_id, nav_label, sec_id + ".html"))
    pages.append(("search", "🔍 Търсене", "search.html"))

    updated_ts = 0
    for name in list(texts) + list(singles):
        updated_ts = max(updated_ts, file_mtime(name))
    updated = datetime.fromtimestamp(updated_ts).strftime("%d.%m.%Y %H:%M")
    now = datetime.now()
    today_str = "%s, %d %s %d" % (WEEKDAYS_BG[now.weekday()], now.day,
                                  MONTHS_BG[now.month - 1], now.year)

    def nav_html(active):
        out = []
        for page_id, label, href in pages:
            cur = ' aria-current="page"' if page_id == active else ""
            out.append('<a href="%s"%s>%s</a>' % (href, cur, esc(label)))
        return "".join(out)

    def shell(active, title, body_html, extra_js=""):
        page = (
            '<!DOCTYPE html>\n<html lang="bg">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>%s — Моите дайджести</title>\n'
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
            '<div class="header-row"><a class="brand" href="index.html">'
            '<img src="favicon.svg" alt="" width="32" height="32">'
            '<span class="brand-name">Моите дайджести</span></a>'
            '<span class="brand-date">' + esc(today_str) + '</span></div>'
            '<nav class="nav" aria-label="Раздели">' + nav_html(active) + '</nav>'
            '</div></header>\n'
            '<main id="main">' + body_html + '</main>\n'
            '<footer><div class="container">'
            '<div class="foot-nav">' + nav_html(active) + '</div>'
            '<p>Последно обновяване: ' + esc(updated) + ' · Обновява се автоматично на всеки час.</p>'
            '<p><a href="feed.xml">RSS емисия — новините</a> · <a href="#top">Нагоре ↑</a></p>'
            '</div></footer>\n'
            '<script>' + JS + '</script>\n' + extra_js +
            '</body>\n</html>\n'
        )
        return page

    def write_page(filename, content):
        with open(os.path.join(SITE_DIR, filename), "w", encoding="utf-8") as f:
            f.write(content)
        return len(content.encode("utf-8"))

    sizes = {}

    # ================= НАЧАЛО =================
    if news:
        latest = news[-1]
        latest_text = texts[latest["name"]]
        hero_html = (
            '<div class="container" id="top"><div class="hero"><p class="kicker">Най-новото</p>'
            '<h1>Новини <span class="hl">%s, %s</span> — <em>%s</em></h1>'
            '<p class="lede">%d новини · %s</p><ul>%s</ul>'
            '<a class="btn-primary" href="news.html#ed-%s">Чети изданието ↓</a></div></div>'
            % (fmt_date(latest["date"]), weekday_bg(latest["date"]),
               PART_LABEL[latest["part"]],
               count_articles(latest_text), PART_EMOJI[latest["part"]],
               "".join("<li>%s</li>" % esc(t) for t in extract_h4_titles(latest_text, 3)),
               esc(news_slug(latest)))
        )
        latest_date = latest["date"]
        today_items = [i for i in news if i["date"] == latest_date]
        today_cards = "".join(news_preview_card(i, texts[i["name"]]) for i in today_items)
    else:
        hero_html = '<div class="container" id="top"></div>'
        today_cards = ""

    # последен дайджест — карта за началната
    digest_card = ""
    if digests:
        daily = [d for d in digests if d["kind"] == "daily"]
        latest_d = daily[0] if daily else digests[0]
        digest_card = (
            '<article class="card"><span class="icon">🗓️</span>'
            '<h3>Събития — %s</h3><p class="meta">%s</p>'
            '<a class="btn-primary" href="events.html#dg-%s">Виж дайджеста ↓</a></article>'
            % (fmt_date(latest_d["date"]), esc(digest_meta(texts[latest_d["name"]])),
               esc(digest_slug(latest_d)))
        )

    # седмицата — първите 3 точки от week-ahead
    week_card = ""
    if "week-ahead.html" in singles:
        week_body = inline_body("week-ahead.html")
        items = []
        for m in re.finditer(r'<div class="item">(.*?)</div>', week_body, re.S):
            t = re.sub(r"<[^>]+>", "", m.group(1))
            t = htmlmod.unescape(t).strip()
            t = re.sub(r"\s+", " ", t)
            if t:
                items.append(t)
            if len(items) >= 3:
                break
        if items:
            week_card = (
                '<article class="card"><span class="icon">📅</span>'
                '<h3>Седмицата напред</h3><ul>%s</ul>'
                '<a class="btn-primary" href="week.html">Цялата седмица →</a></article>'
                % "".join("<li>%s</li>" % esc(t) for t in items)
            )

    # решетка с разделите
    grid_cards = []
    grid_cards.append(
        '<article class="card"><span class="icon">📰</span><h3>Новини</h3>'
        '<p class="meta">%d издания · сутрин, следобед и вечер</p>'
        '<a class="btn-ghost" href="news.html">Отвори →</a></article>' % len(news)
    )
    grid_cards.append(
        '<article class="card"><span class="icon">🗓️</span><h3>Събития</h3>'
        '<p class="meta">%d дайджеста · дневен, седмичен и вечерни</p>'
        '<a class="btn-ghost" href="events.html">Отвори →</a></article>' % len(digests)
    )
    for sec_id, nav_label, title, intro, fname, emoji in single_defs:
        if fname not in singles:
            continue
        meta = intro
        grid_cards.append(
            '<article class="card"><span class="icon">%s</span><h3>%s</h3>'
            '<p class="meta">%s</p>'
            '<a class="btn-ghost" href="%s.html">Отвори →</a></article>'
            % (emoji, esc(title), esc(meta), sec_id)
        )

    home_body = (
        hero_html
        + '<section aria-labelledby="today-h"><div class="container">'
          '<div class="section-head"><h2 id="today-h">Днес</h2>'
          '<a href="news.html">Всички новини →</a></div>'
          '<div class="grid">%s%s%s</div>'
          '</div></section>'
        % (today_cards, digest_card, week_card)
        + '<section aria-labelledby="sections-h"><div class="container">'
          '<h2 id="sections-h">Раздели</h2>'
          '<p class="section-intro">Всичко на едно място — избери раздел и чети на място.</p>'
          '<div class="grid">%s</div>'
          '</div></section>' % "".join(grid_cards)
    )
    sizes["index.html"] = write_page(
        "index.html", shell("index", "Новини, събития и справки", home_body))

    # ================= НОВИНИ =================
    if news:
        latest = news[-1]
        latest_date = latest["date"]
        today_items = [i for i in news if i["date"] == latest_date]
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
        news_body = (
            '<div class="container" id="top"><div class="page-hero">'
            '<p class="kicker">Новини</p><h1>Новини — сутрин, следобед и вечер</h1>'
            '<p class="lede">%d издания · чети на място, без да отваряш отделни файлове. '
            'Всяко издание има търсене и филтри вътре.</p></div>'
            '<div class="searchbar" role="search">'
            '<input id="q" type="search" placeholder="Търси в новините…" aria-label="Търси в новините">'
            '<p class="count-line" id="count" aria-live="polite"></p>'
            '<p class="no-results" id="no-results" hidden>Няма съвпадения — опитай с по-кратка дума.</p>'
            '</div></div>'
            '<section aria-labelledby="today-h"><div class="container">'
            '<h2 id="today-h">%s, %s</h2>%s'
            '<h3 style="margin:28px 0 12px;font-family:var(--font-serif);font-size:20px">Архив</h3>%s'
            '</div></section>'
            % (len(news), fmt_date(latest_date), weekday_bg(latest_date),
               today_details, archive_html)
        )
        sizes["news.html"] = write_page(
            "news.html", shell("news", "Новини", news_body))

    # ================= СЪБИТИЯ =================
    if digests:
        daily = [d for d in digests if d["kind"] == "daily"]
        latest_d = daily[0] if daily else digests[0]
        rest = [d for d in digests if d is not latest_d]
        archive_html = "".join(digest_row(d, texts[d["name"]]) for d in rest)
        other_html = ""
        if other_events:
            other_html = (
                '<h3 style="margin:28px 0 12px;font-family:var(--font-serif);font-size:20px">Още</h3>'
                + "".join(other_event_row(o, read_file(o["name"])) for o in other_events)
            )
        events_body = (
            '<div class="container" id="top"><div class="page-hero">'
            '<p class="kicker">Събития</p><h1>Дневен дайджест със събития</h1>'
            '<p class="lede">%s · %s. Филтрите са вътре в дайджеста: търсене, дни и категории.</p></div>'
            '<div class="searchbar" role="search">'
            '<input id="q" type="search" placeholder="Търси в дайджестите…" aria-label="Търси в дайджестите">'
            '<p class="count-line" id="count" aria-live="polite"></p>'
            '<p class="no-results" id="no-results" hidden>Няма съвпадения — опитай с по-кратка дума.</p>'
            '</div></div>'
            '<section aria-labelledby="latest-h"><div class="container">'
            '<h2 id="latest-h">Най-новият дайджест</h2>%s'
            '<h3 style="margin:28px 0 12px;font-family:var(--font-serif);font-size:20px">По-стари дайджести</h3>%s%s'
            '</div></section>'
            % (fmt_date(latest_d["date"]), esc(digest_meta(texts[latest_d["name"]])),
               digest_row(latest_d, texts[latest_d["name"]], lazy=False),
               archive_html, other_html)
        )
        sizes["events.html"] = write_page(
            "events.html", shell("events", "Събития", events_body))

    # ================= ЕДИНИЧНИ СТРАНИЦИ =================
    for sec_id, nav_label, title, intro, fname, emoji in single_defs:
        if fname not in singles:
            continue
        body = (
            '<div class="container" id="top"><div class="page-hero">'
            '<p class="kicker">%s</p><h1>%s</h1>'
            '<p class="lede">%s</p></div></div>'
            '<section><div class="container">%s</div></section>'
            % (esc(nav_label), esc(title), esc(intro), single_body(fname))
        )
        sizes[sec_id + ".html"] = write_page(
            sec_id + ".html", shell(sec_id, title, body))

    # ================= ТЪРСЕНЕ =================
    search_entries = []
    for item in news:
        search_entries.append({
            "t": "Новини %s — %s" % (fmt_date(item["date"]), PART_LABEL[item["part"]]),
            "d": "%s, %s" % (fmt_date(item["date"]), weekday_bg(item["date"])),
            "k": "Новини",
            "u": "news.html#ed-%s" % news_slug(item),
            "s": " ".join(extract_h4_titles(texts[item["name"]], 5)),
        })
    for item in digests:
        title = "%s, %s" % (fmt_date(item["date"]), weekday_bg(item["date"])) \
            if item["kind"] == "daily" else item["label"]
        search_entries.append({
            "t": "Дайджест — %s" % title,
            "d": fmt_date(item["date"]),
            "k": "Събития",
            "u": "events.html#dg-%s" % digest_slug(item),
            "s": " ".join(extract_first_headings(texts[item["name"]], 5)),
        })
    for sec_id, nav_label, title, intro, fname, emoji in single_defs:
        if fname not in singles:
            continue
        search_entries.append({
            "t": title, "d": "", "k": "Страница",
            "u": "%s.html" % sec_id,
            "s": plain_text(read_file(fname), 300),
        })
    if "week-ahead.html" in singles:
        week_body = inline_body("week-ahead.html")
        for m in re.finditer(r'<div class="item">(.*?)</div>', week_body, re.S):
            t = re.sub(r"<[^>]+>", "", m.group(1))
            t = htmlmod.unescape(t).strip()
            t = re.sub(r"\s+", " ", t)
            if t:
                search_entries.append({
                    "t": t[:120], "d": "", "k": "Седмицата",
                    "u": "week.html", "s": t,
                })
    with open(os.path.join(SITE_DIR, "search.json"), "w", encoding="utf-8") as f:
        json.dump(search_entries, f, ensure_ascii=False)
    search_body = (
        '<div class="container" id="top"><div class="page-hero">'
        '<p class="kicker">Търсене</p><h1>Търси в дайджестите</h1>'
        '<p class="lede">В изданията, събитията и седмицата — наведнъж.</p></div>'
        '<div class="searchbar" role="search">'
        '<input id="q" type="search" placeholder="Напиши дума — например „преход“, „джаз“, „Подари Време“…“ aria-label="Търси в дайджестите">'
        '<p class="count-line" id="count" aria-live="polite"></p>'
        '</div><div id="results"><p class="no-results">Напиши дума — търси в изданията, събитията и седмицата.</p></div>'
        '</div>'
    )
    sizes["search.html"] = write_page(
        "search.html", shell("search", "Търсене", search_body,
                             extra_js='<script>' + SEARCH_JS + '</script>\n'))

    # ================= RSS =================
    with open(os.path.join(SITE_DIR, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(build_feed(news))
    sizes["feed.xml"] = os.path.getsize(os.path.join(SITE_DIR, "feed.xml"))
    sizes["search.json"] = os.path.getsize(os.path.join(SITE_DIR, "search.json"))

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
        "other": len(other_events),
    }
    print("INDEX: total=%d news=%d digest=%d podari=%d radar=%d cars=%d aiplan=%d "
          "events=%d week=%d weather=%d subs=%d scout=%d other=%d updated=%s"
          % (counts["total"], counts["news"], counts["digest"], counts["podari"],
             counts["radar"], counts["cars"], counts["aiplan"], counts["events"],
             counts["week"], counts["weather"], counts["subs"], counts["scout"],
             counts["other"], updated))
    print("INDEX-SIZE: " + " ".join("%s=%d" % (k, v) for k, v in sorted(sizes.items())))


if __name__ == "__main__":
    main()
