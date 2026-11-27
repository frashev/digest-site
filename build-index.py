#!/usr/bin/env python3
# build-index.py — генерира МНОГОСТРАНИЧЕН сайт с дайджестите (v3: данни, не файлове).
# Дизайн: mobile-first, топла хартия (#FBF9F3), един тухлен акцент (#9C493D),
# лепкаво меню с къси етикети (активната страница е маркирана, менюто се
# скролва до нея). Всяка страница е отделна:
# index (начало), news (новини), events (събития), vreme,
# scout (ако има), search (глобално търсене).
# ДАННИТЕ СЕ ЧЕТАТ НА СТРАНИЦАТА, БЕЗ ОТВАРЯНЕ НА HTML ФАЙЛОВЕ:
# - новини: статиите от най-новото издание се парсват и се показват директно
#   (по дни и издания, с търсене и филтър по категория); старите издания не се показват.
# - събития: всички събрани събития от events-registry.json, от днес нататък,
#   подредени по дни; старите не се показват; дайджест файловете не се ползват.
# - време: weather.html се вгражда директно (почасова прогноза 24ч x 7 дни).
# - Подари Време: СКРИТО от сайта (25.11.2026, по искане на Philippe); източниците
#   остават локално (podari-trips.json, podari-site.json, podari-map.html).
# Малките файлове без скриптове се вграждат директно. Глобалното търсене
# чете search.json. Без външни зависимости. Пуска се от publish.ps1 на PC-то.
# Изход: index.html, news.html, events.html, vreme.html,
# scout.html,
# search.html, search.json, feed.xml.
import html as htmlmod
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta

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
GENERATED = ("index.html", "news.html", "events.html", "vreme.html",
             "podari.html", "radar.html", "cars.html", "aiplan.html",
             "scout.html", "search.html", "assistants.html")

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



def count_articles(html_text):
    return len(re.findall(r"<article[^>]*>", html_text))


def truncate_text(s, limit=240):
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0] + "…"


NEWS_CAT_LABEL = {"ai": "🤖 AI и технологии", "bg": "🇧🇬 България", "world": "🌍 Свят"}
# Източник на събитие (групиран за филтъра) — суровите стойности от регистъра
SRC_LABEL = {"facebook-discover": "Facebook", "facebook-browser-search": "Facebook",
             "togeda-api (PC feed)": "Togeda", "event-ai-extractor": "Колектор",
             "tazivecher.bg": "Уеб", "allevents": "Уеб", "allevents.in": "Уеб",
             "visitsofia.bg": "Уеб", "web-search": "Уеб", "gemini": "Уеб"}


def src_label(raw):
    return SRC_LABEL.get((raw or "").strip(), "Други")


def parse_news_articles(html_text):
    """Всички статии от едно издание: заглавие, текст, източник, категория."""
    out = []
    for m in re.finditer(r'<article class="card"([^>]*)>(.*?)</article>', html_text, re.S):
        attrs, body = m.group(1), m.group(2)

        def attr(name):
            mm = re.search(r'%s="([^"]*)"' % name, attrs)
            return mm.group(1) if mm else ""

        color_m = re.search(r"border-left-color:([^;\"']+)", attrs)
        color = color_m.group(1).strip() if color_m else "#9C493D"
        title_m = re.search(r"<h4[^>]*>(.*?)</h4>", body, re.S)
        title = re.sub(r"<[^>]+>", "", title_m.group(1)) if title_m else ""
        title = htmlmod.unescape(re.sub(r"\s+", " ", title)).strip()
        text_m = re.search(r"</h4>\s*<p>(.*?)</p>", body, re.S)
        text = re.sub(r"<[^>]+>", "", text_m.group(1)) if text_m else ""
        text = htmlmod.unescape(re.sub(r"\s+", " ", text)).strip()
        link_m = re.search(r'<a href="([^"]+)"[^>]*>(.*?)</a>', body, re.S)
        link = link_m.group(1) if link_m else ""
        link_label = re.sub(r"<[^>]+>", "", link_m.group(2)) if link_m else ""
        link_label = htmlmod.unescape(re.sub(r"\s+", " ", link_label)).strip()
        if title:
            out.append({"day": attr("data-day"), "ed": attr("data-ed"),
                        "cat": attr("data-cat"), "color": color,
                        "title": title, "text": text, "link": link,
                        "link_label": link_label})
    return out


_SAFE_URL = re.compile(r"^https?://[^\s]+$", re.I)
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def safe_url(u):
    """Само http(s) адреси; javascript:, data: и всичко друго -> празно."""
    u = (u or "").strip()
    return u if _SAFE_URL.match(u) else ""


def safe_color(c, default="#9C493D"):
    """Само #hex цвят в style=; всичко друго -> цвета по подразбиране."""
    c = (c or "").strip()
    return c if _HEX_COLOR.match(c) else default


def news_item_html(a):
    search = "%s %s %s %s" % (a["day"], a["cat"], a["title"], a["text"])
    href = safe_url(a.get("link"))
    link = ('<p class="links"><a href="%s" target="_blank" rel="noopener">%s</a></p>'
            % (esc(href), esc(a["link_label"] or "Източник"))) if href else ""
    color = safe_color(a.get("color"))
    chip = NEWS_CAT_LABEL.get(a["cat"], "")
    return (
        '<article class="news-item" data-cat="%s" data-day="%s" data-search="%s" style="border-left-color:%s">'
        '<span class="news-chip" style="border-color:%s;color:%s">%s</span>'
        '<h4>%s</h4><p>%s</p>%s</article>'
        % (esc(a["cat"]), esc(a["day"]), esc(search), esc(color), esc(color),
           esc(color), esc(chip), esc(a["title"]), esc(a["text"]), link)
    )


def load_events_registry():
    """Всички събрани събития от регистъра (ако файлът е в SITE_DIR)."""
    path = os.path.join(SITE_DIR, "events-registry.json")
    if not os.path.exists(path):
        print("WARNING: events-registry.json missing; events.html is kept as it was", file=sys.stderr)
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    evs = data.get("events", data) if isinstance(data, dict) else data
    return [e for e in evs if isinstance(e, dict)]


def podari_day_badge(iso, today):
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    diff = (d - today).days
    if diff == 0:
        return '<span class="ev-free" style="background:#FFEBEE;color:#B71C1C">ДНЕС</span>'
    if diff == 1:
        return '<span class="ev-free" style="background:#FFF3E0;color:#E65100">УТРЕ</span>'
    return '<span class="ev-cat">след %d дни</span>' % diff


def podari_places_badge(n):
    if n is None:
        return '<span class="ev-free">Онлайн</span>'
    if n == 0:
        return '<span class="ev-free" style="background:#FFEBEE;color:#B71C1C">Няма места</span>'
    if n <= 3:
        return ('<span class="ev-free" style="background:#FFF3E0;color:#E65100">'
                'Оставащи места: %d — малко</span>' % n)
    return '<span class="ev-free">Оставащи места: %d</span>' % n


# Разстояния от София (минути с кола, км) — главното копие е CITY_GEO в
# build-podari-vreme-html.py; петъчната проверка обновява и двете.
PV_GEO = {
    "Долна баня": (66, 79), "Звъничево": (83, 119), "Мездра": (84, 102),
    "Самоков": (86, 60), "Пловдив": (92, 144), "Враца": (93, 111),
    "Пещера": (98, 131), "Берковица": (98, 86), "Брацигово": (107, 134),
    "Велинград": (108, 134), "Монтана": (124, 109), "Гаврил Геново": (129, 109),
    "Карлово": (130, 138), "Плевен": (134, 164), "Хасково": (136, 227),
    "Стара Загора": (140, 231), "Петрич": (145, 181),
    "Велико Търново": (179, 220), "Стражица": (215, 255),
}


def fmt_drive(mins):
    if mins >= 60:
        return "%dч%02d" % (mins // 60, mins % 60)
    return "%d мин" % mins


def _dep_mins(dep_txt):
    """Първият час ЧЧ:ММ от текста за тръгване, в минути от полунощ (9999 ако няма)."""
    m = re.search(r"(\d{1,2}):(\d{2})", dep_txt or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 9999


def podari_near_table(podari_json, today_iso, trips_url):
    """Таблица „Списък по близост до София": предстоящите посещения (от София
    и местните групи), подредени по подразбиране ХРОНОЛОГИЧНО (дата, после час
    на тръгване) — най-близките по време първи. Колоните Дата / Разстояние /
    Тръгване се сортират от малките бутони в заглавията им (клик = смяна на
    посоката; вторичните ключове са дата, час и място)."""
    rows = []
    for t in podari_json.get("trips_sofia", []):
        if t["date"] < today_iso:
            continue
        dep = "%s · %s" % (t["dep"], t["point"])
        rows.append({"date": t["date"], "place": t["place"], "dep": dep,
                     "dep_mins": _dep_mins(dep),
                     "km": PV_GEO.get(t["place"], (0, 99999))[1],
                     "places": t["places"], "url": trips_url})
    for t in podari_json.get("trips_local", []):
        if t["date"] < today_iso:
            continue
        local_only = t.get("local_only", True)
        dep = ("местно · пред дома %s" % t["home"] if local_only
               else "пред дома %s" % t["home"])
        rows.append({"date": t["date"], "place": t["place"], "dep": dep,
                     "dep_mins": _dep_mins(dep),
                     "km": PV_GEO.get(t["place"], (0, 99999))[1],
                     "places": t["places"], "url": trips_url})
    if not rows:
        return ""
    rows.sort(key=lambda r: (r["date"], r["dep_mins"], r["place"]))
    out = ['<section id="pv-near-sofia"><div class="container"><h2>Списък по близост до София</h2>'
           '<p class="meta">Предстоящите посещения, подредени по дата — най-близките по време първи. '
           'Сортирай от бутоните в заглавията на колоните: по дата, по разстояние или по час на тръгване.</p>'
           '<div class="pv-table-wrap"><table class="pv-table" id="pvNearTable">'
           '<thead><tr>'
           '<th><button class="sort-btn" data-sort="date" data-dir="asc">Дата <span class="sort-arrow">▲</span></button></th>'
           '<th>Място</th>'
           '<th><button class="sort-btn" data-sort="km" data-dir="asc">Разстояние <span class="sort-arrow"></span></button></th>'
           '<th><button class="sort-btn" data-sort="dep" data-dir="asc">Тръгване <span class="sort-arrow"></span></button></th>'
           '<th>Дейност</th><th></th></tr></thead><tbody>']
    for r in rows:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        g = PV_GEO.get(r["place"])
        dist = "%d км · ~%s" % (g[1], fmt_drive(g[0])) if g else "—"
        if r["places"] == 0:
            signup = '<span style="color:#B71C1C">Няма места</span>'
        else:
            signup = ('<a href="%s" target="_blank" rel="noopener">Запиши се →</a>'
                      % esc(r["url"]))
        out.append(
            '<tr data-date="%s" data-km="%d" data-dep="%d" data-place="%s">'
            '<td>%s, %s</td><td>%s</td><td>%s</td><td>%s</td><td>Посещение при децата</td><td>%s</td></tr>'
            % (r["date"], r["km"], r["dep_mins"], esc(r["place"]),
               weekday_bg(dt)[:3], dt.strftime("%d.%m"), esc(r["place"]), dist,
               esc(r["dep"]), signup)
        )
    out.append('</tbody></table></div>'
               '<p class="meta">Точната програма за всяко посещение е на страницата за записване — след вход '
               'в профила на podarivreme.org. „Местно“ означава, че групата е от града и няма '
               'организирано тръгване от София.</p>'
               '</div></section>')
    return "".join(out)


def podari_card_html(it):
    search = "%s %s %s" % (it["date"], it["place"], it["meta"])
    return (
        '<article class="ev-card" data-kind="%s" data-search="%s">'
        '<div><span class="ev-cat">%s</span></div>'
        '<h3>%s</h3><p class="ev-venue">%s</p>'
        '<p>%s</p>'
        '<p class="ev-links"><a href="%s" target="_blank" rel="noopener">Запиши се →</a></p></article>'
        % (esc(it["kind"]), esc(search), esc(it["cat"]), esc(it["place"]),
           esc(it["meta"]), podari_places_badge(it["places"]), esc(it["url"]))
    )


def podari_site_sections(site):
    """Нови секции за страницата Подари Време — цялото съдържание на сайта на
    фондацията от podari-site.json (карта на сайта: podari-site-map.md):
    мисия в числа, как се става доброволец, Академия, Училище за работа,
    документи, блог, медии, подкаст, дарения, контакти."""
    if not site:
        return ""
    parts = []
    m = site.get("mission", {})
    if m:
        parts.append(
            '<section id="pv-mission"><div class="container"><h2>Мисията в числа</h2>'
            '<p class="meta">„%s“</p><div class="grid">'
            '<article class="card"><p class="pv-big">%d</p><p class="meta">години с децата</p></article>'
            '<article class="card"><p class="pv-big">%d</p><p class="meta">активно ангажирани доброволци</p></article>'
            '<article class="card"><p class="pv-big">%d</p><p class="meta">деца, подкрепяни дългосрочно</p></article>'
            '<article class="card"><p class="pv-big">%d</p><p class="meta">институции в страната</p></article>'
            '</div><p class="meta">Над %d подарени дни всяка година. %s</p></div></section>'
            % (esc(m.get("quote", "")), m.get("years", 0), m.get("volunteers", 0),
               m.get("children", 0), m.get("institutions", 0),
               m.get("days_per_year", 0), esc(m.get("license", "")))
        )
    steps = site.get("how_to_join", [])
    rules = site.get("guide_rules", [])
    if steps:
        cards = "".join(
            '<article class="card"><span class="pv-step-n">%d</span><h3>%s</h3>'
            '<p class="meta">%s</p><p><a href="%s" target="_blank" rel="noopener">Отвори →</a></p></article>'
            % (i + 1, esc(s.get("title", "")), esc(s.get("text", "")),
               esc(s.get("url", "")))
            for i, s in enumerate(steps)
        )
        rules_html = ""
        if rules:
            rules_html = (
                '<h3>Петте правила на доброволеца</h3><ul class="pv-links">%s</ul>'
                '<p class="meta"><a href="%s" target="_blank" rel="noopener">'
                'Наръчникът — Първи стъпки →</a></p>'
                % ("".join("<li>♦ %s</li>" % esc(r) for r in rules),
                   esc(site.get("guide_url", "")))
            )
        parts.append(
            '<section id="pv-join"><div class="container"><h2>Как се става доброволец</h2>'
            '<div class="grid">%s</div>%s</div></section>' % (cards, rules_html)
        )
    ac = site.get("academy", {})
    if ac:
        stages = "".join(
            '<article class="card"><p class="meta">%s · %s</p><h3>%s — %s</h3>'
            '<p class="meta">%s</p><p class="meta">Предмети: %s</p>'
            '<p class="meta">Формат: %s</p></article>'
            % (esc(s.get("stage", "")), esc(s.get("classes", "")),
               esc(s.get("name", "")), esc(s.get("title", "")),
               esc(s.get("text", "")), esc(s.get("subjects", "")),
               esc(s.get("format", "")))
            for s in ac.get("stages", [])
        )
        price = "".join(
            '<p class="meta"><b>%s</b> — %s</p>'
            % (esc(p.get("amount", "")), esc(p.get("text", "")))
            for p in ac.get("pricing", [])
        )
        parts.append(
            '<section id="pv-academy"><div class="container"><h2>Академията</h2>'
            '<p class="meta">%s</p><div class="grid">%s</div>%s'
            '<p class="meta">%s</p>'
            '<p><a href="%s" target="_blank" rel="noopener">Академията на podarivreme.org →</a></p>'
            '</div></section>'
            % (esc(ac.get("intro", "")), stages, price,
               esc(ac.get("teacher_call", "")), esc(ac.get("url", "")))
        )
    ws = site.get("work_school", {})
    if ws:
        parts.append(
            '<section id="pv-work"><div class="container"><h2>%s</h2><article class="card">'
            '<p class="meta">%s</p><p class="meta">%s · %d младежи от цялата страна · '
            'база: %s</p><p class="meta">Екипи: %s.</p><p class="meta">%s</p>'
            '<p class="meta">%s</p>'
            '<p><a href="%s" target="_blank" rel="noopener">Училище за работа →</a></p>'
            '</article></div></section>'
            % (esc(ws.get("title", "")), esc(ws.get("desc", "")),
               esc(ws.get("dates", "")), ws.get("youths", 0), esc(ws.get("base", "")),
               esc(", ".join(ws.get("teams", []))), esc(ws.get("mentor", "")),
               esc(ws.get("note", "")), esc(ws.get("url", "")))
        )
    docs = site.get("documents", [])
    if docs:
        items = "".join(
            '<li><a href="%s" target="_blank" rel="noopener">%s</a></li>'
            % (esc(d.get("url", "")), esc(d.get("title", "")))
            for d in docs
        )
        parts.append(
            '<section id="pv-docs"><div class="container"><h2>Документи</h2>'
            '<ul class="pv-links">%s</ul>'
            '<p class="meta"><a href="%s" target="_blank" rel="noopener">'
            'Всички документи на сайта на фондацията →</a></p></div></section>'
            % (items, esc(site.get("documents_url", "")))
        )
    stories = site.get("stories", [])
    if stories:
        items = "".join(
            '<li><a href="%s" target="_blank" rel="noopener">%s</a>'
            '<span class="pv-date">%s</span></li>'
            % (esc(s.get("url", "")), esc(s.get("title", "")),
               esc(s.get("date", "")))
            for s in stories
        )
        parts.append(
            '<section id="pv-stories"><div class="container"><h2>Истории от блога</h2>'
            '<ul class="pv-links">%s</ul>'
            '<p class="meta"><a href="%s" target="_blank" rel="noopener">'
            'Блогът на фондацията →</a></p></div></section>'
            % (items, esc(site.get("stories_url", "")))
        )
    media = site.get("media", [])
    if media:
        items = "".join(
            '<li><a href="%s" target="_blank" rel="noopener">%s</a>'
            '<span class="pv-date">%s · %s</span></li>'
            % (esc(x.get("url", "")), esc(x.get("title", "")),
               esc(x.get("outlet", "")), esc(x.get("date", "")))
            for x in media
        )
        parts.append(
            '<section id="pv-media"><div class="container"><h2>В медиите</h2>'
            '<ul class="pv-links">%s</ul>'
            '<p class="meta"><a href="%s" target="_blank" rel="noopener">'
            'Всички медийни участия →</a></p></div></section>'
            % (items, esc(site.get("media_url", "")))
        )
    pc = site.get("podcast", {})
    nl = site.get("newsletter", {})
    if pc or nl:
        pc_links = ""
        if pc:
            pc_links = " · ".join(
                '<a href="%s" target="_blank" rel="noopener">%s</a>'
                % (esc(u), esc(name))
                for name, u in pc.get("links", {}).items()
            )
            pc_links = ('<h3>%s</h3><p class="meta">%s</p><p>%s</p>'
                        '<p><a href="%s" target="_blank" rel="noopener">'
                        'Подкастът →</a></p>'
                        % (esc(pc.get("title", "")), esc(pc.get("desc", "")),
                           pc_links, esc(pc.get("url", ""))))
        nl_html = ""
        if nl:
            nl_html = ('<h3>%s</h3><p class="meta">%s</p>'
                       '<p><a href="%s" target="_blank" rel="noopener">'
                       'Абонирай се →</a></p>'
                       % (esc(nl.get("title", "")), esc(nl.get("desc", "")),
                          esc(nl.get("url", ""))))
        parts.append(
            '<section id="pv-podcast"><div class="container"><h2>Подкаст и бюлетин</h2>'
            '<article class="card">%s%s</article></div></section>'
            % (pc_links, nl_html)
        )
    sup = site.get("support", {})
    if sup:
        st = sup.get("stats", {})
        amounts = "".join(
            '<span class="pv-amount"><b>%s</b><br>%s</span>'
            % (esc(a.get("amount", "")), esc(a.get("effect", "")))
            for a in sup.get("amounts", [])
        )
        bank = sup.get("bank", {})
        parts.append(
            '<section id="pv-support"><div class="container"><h2>Подкрепи</h2><article class="card">'
            '<p class="meta">Изпълнени добрини до момента: +%d картички · +%d мисии · '
            '+%d продукта.</p><div class="pv-donate">%s</div>'
            '<p class="meta">С банков превод: IBAN %s · BIC %s · %s · титуляр: %s</p>'
            '<p><a href="%s" target="_blank" rel="noopener">Дари на podarivreme.org →</a></p>'
            '</article></div></section>'
            % (st.get("cards", 0), st.get("missions", 0), st.get("products", 0),
               amounts, esc(bank.get("iban", "")), esc(bank.get("bic", "")),
               esc(bank.get("bank", "")), esc(bank.get("holder", "")),
               esc(sup.get("url", "")))
        )
    ct = site.get("contacts", {})
    if ct:
        parts.append(
            '<section id="pv-contacts"><div class="container"><article class="card"><h2>Контакти</h2>'
            '<p class="meta">%s · <a href="mailto:%s">%s</a> · %s · %s · '
            '<a href="%s" target="_blank" rel="noopener">podarivreme.org</a></p>'
            '<p class="meta">Въпроси към фондацията: <a href="mailto:%s">%s</a></p>'
            '<p class="podari-note">Данните за посещенията се обновяват всеки петък от '
            'сайта на фондацията и писмата ѝ. Директна жива проверка от браузъра не е '
            'възможна — сайтът на фондацията не позволява заявки от други страници '
            '(CORS). Съдържанието на тази страница е от сайта на фондацията, '
            'прегледано на %s.</p>'
            '</article></div></section>'
            % (esc(ct.get("address", "")), esc(ct.get("email", "")),
               esc(ct.get("email", "")), esc(ct.get("phone", "")),
               esc(ct.get("coordinator", "")), esc(ct.get("url", "")),
               esc(ct.get("questions_email", "")),
               esc(ct.get("questions_email", "")),
               esc(site.get("updated", "")))
        )
    return "".join(parts)


def event_card_html(e, new_date=None):
    name = e.get("name") or ""
    start = e.get("start") or ""
    end = e.get("end") or ""
    time_txt = "%s–%s" % (start, end) if end else start
    venue = e.get("venue") or ""
    address = e.get("address") or ""
    place = "%s, %s" % (venue, address) if address and address != venue else venue
    cat = e.get("category") or ""
    desc = e.get("description_bg") or ""
    if desc:
        if len(desc) > 240:
            desc_html = ('<p class="ev-desc">%s</p>'
                         '<details class="ev-desc"><summary>Цялото описание</summary>'
                         '<p>%s</p></details>'
                         % (esc(truncate_text(desc, 240)), esc(desc)))
        else:
            desc_html = '<p class="ev-desc">%s</p>' % esc(desc)
    else:
        desc_html = ""
    free_badge = ' <span class="ev-free">🆓 Безплатно</span>' if e.get("free") else ""
    cat_chip = '<span class="ev-cat">%s</span>' % esc(cat) if cat else ""
    links = []
    if safe_url(e.get("link")):
        links.append('<a href="%s" target="_blank" rel="noopener">Към събитието →</a>'
                     % esc(safe_url(e.get("link"))))
    if e.get("maps_query"):
        links.append('<a href="https://www.google.com/maps/search/?api=1&query=%s" '
                     'target="_blank" rel="noopener">Карта</a>'
                     % urllib.parse.quote(e["maps_query"]))
    search = "%s %s %s %s %s" % (e.get("date", ""), name, place, cat, desc)
    new = "1" if (new_date and e.get("first_seen") == new_date) else "0"
    return (
        '<article class="ev-card" id="ev-%s" data-search="%s" data-day="%s" '
        'data-cat="%s" data-src="%s" data-free="%s" data-new="%s" data-time="%s" data-far="%s">'
        '<div><span class="ev-time">%s</span>%s %s</div>'
        '<h3>%s</h3><p class="ev-venue">%s</p>%s'
        '<p class="ev-links">%s</p></article>'
        % (esc(str(e.get("number", ""))), esc(search), esc(e.get("date", "")),
           esc(cat), esc(src_label(e.get("source"))),
           "1" if e.get("free") else "0", new,
           "0" if e.get("time_unknown") else "1",
           "1" if e.get("far") else "0",
           esc(time_txt), free_badge, cat_chip, esc(name), esc(place), desc_html,
           " ".join(links))
    )


def plain_text(html_text, limit=600):
    t = re.sub(r"<script.*?</script>", " ", html_text, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


_ATTR_VAL = r"""("[^"]*"|'[^']*'|[^\s>]+)"""
_TAG = re.compile(r"""<[a-zA-Z][^\s/>]*(?:"[^"]*"|'[^']*'|[^'">])*>""")


def _safe_attr(m):
    """href/src само към http(s), mailto, tel, # или относителен път (src и data:image/); иначе -> "#"."""
    name, raw = m.group(1), m.group(2).strip("\"'")
    plain = re.sub(r"[\x00-\x20]", "", htmlmod.unescape(raw)).lower()
    scheme = re.match(r"^([a-z][a-z0-9+.-]*):", plain)
    if not scheme or scheme.group(1) in ("http", "https", "mailto", "tel"):
        return m.group(0)
    if name.lower() == "src" and plain.startswith("data:image/") and not plain.startswith("data:image/svg"):
        return m.group(0)
    return '%s="#"' % name


_ATTR = re.compile(r"""([^\s"'>/=]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?""")
_URL_ATTRS = ("href", "src", "action", "formaction", "xlink:href")


def _clean_tag(m):
    """Сглобява тага наново атрибут по атрибут: без on*= и srcdoc, адресите минават през _safe_attr."""
    tag = m.group(0)
    nm = re.match(r"<([a-zA-Z][^\s/>]*)", tag)
    rest = tag[nm.end():].rstrip(">").rstrip()
    closing = "/" if rest.endswith("/") else ""
    out = []
    for am in _ATTR.finditer(rest):
        key = am.group(1).lower()
        if key.startswith("on") or key == "srcdoc":
            continue
        if am.group(2) is None:
            out.append(am.group(1))
            continue
        piece = "%s=%s" % (am.group(1), am.group(2))
        if key in _URL_ATTRS:
            piece = re.sub(r"^([^=]+)=(.*)$", _safe_attr, piece, flags=re.S)
        out.append(piece)
    return "<%s%s%s>" % (nm.group(1), "".join(" " + x for x in out), closing)


def inline_body(name):
    """Връща тялото на малък файл без скриптове, стилове, вградени рамки, без първия <h1>, без on*= и опасни адреси."""
    text = read_file(name)
    m = re.search(r"<body>(.*?)</body>", text, re.S)
    body = m.group(1) if m else text
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
    body = re.sub(r"<(script|style|iframe|object|embed|template|noscript)\b.*?</\1\s*>", "", body, flags=re.S | re.I)
    body = re.sub(r"<(script|style|iframe|object|embed|meta|base|link)\b[^>]*>", "", body, flags=re.I)
    body = _TAG.sub(_clean_tag, body)
    return body.strip()


def is_inlineable(name):
    text = read_file(name).lower()
    return "<script" not in text and 'id="' not in text


def scan():
    names = [n for n in os.listdir(SITE_DIR)
             if n.endswith(".html") and n not in GENERATED
             and n != "podari-map.html"  # фрагмент за страницата Подари Време, не е съдържание
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
html:focus-within{scroll-behavior:smooth}
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
@media (max-width:600px){.brand-date{display:none}}
.nav{border-top:1px solid var(--border)}
.nav-inner{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding:2px 16px 10px;max-width:1240px;margin:0 auto;-webkit-overflow-scrolling:touch}
.nav-inner::-webkit-scrollbar{display:none}
.nav a{flex:none;padding:12px 14px;border-radius:var(--r-pill);color:var(--muted);text-decoration:none;font-size:15px;font-weight:500;min-height:44px;display:inline-flex;align-items:center;touch-action:manipulation}
.nav a[aria-current="page"]{background:var(--accent-soft);color:var(--ink);font-weight:600}
.page-hero{background:linear-gradient(160deg,#FFF6EC 0%,#FFFFFF 60%);border:1px solid var(--border);border-radius:var(--r-xl);box-shadow:var(--shadow-card);padding:24px;margin:24px 0 8px}
.page-hero .kicker{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
.page-hero h1{font-size:clamp(26px,5vw,34px);line-height:1.15;margin:8px 0 6px;letter-spacing:-.01em}
.page-hero p.lede{color:var(--muted);margin:6px 0 0}
.hero{background:linear-gradient(160deg,#FFF6EC 0%,#FFFFFF 60%);border:1px solid var(--border);border-radius:var(--r-xl);box-shadow:var(--shadow-card);padding:24px;margin:24px 0 8px;display:flex;gap:24px;align-items:center}
.hero-text{flex:1;min-width:0}
.hero-art{flex:0 0 240px}
.hero-art svg{width:100%;height:auto;display:block}
@media (max-width:700px){.hero{flex-direction:column;align-items:stretch}.hero-art{flex-basis:auto;width:100%;max-width:300px;margin:0 auto}}
.glance-big{font-size:26px;font-weight:700;line-height:1.2;margin:2px 0 6px}
.week-strip{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px}
.week-day{display:block;text-align:center;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 2px;text-decoration:none;color:var(--text)}
.week-day:hover{border-color:var(--accent)}
.week-day.today{border-color:var(--accent);background:var(--accent-soft)}
.week-day .wd{display:block;font-size:12px;color:var(--muted)}
.week-day .wn{display:block;font-size:18px;font-weight:700;line-height:1.3}
.week-day .wc{display:block;font-size:12px;color:var(--muted)}
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
/* v3: данни директно на страницата — време, новини, събития */
.wx-day{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);box-shadow:var(--shadow-card);margin:0 0 14px;padding:16px}
.wx-head{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline;justify-content:space-between;margin-bottom:10px}
.wx-date{font-size:18px;font-weight:700;font-family:var(--font-serif)}
.wx-dow{color:var(--muted);font-size:14px}
.wx-sum{font-size:13px;color:var(--muted)}
.wx-strip{display:grid;grid-template-columns:repeat(auto-fill,minmax(84px,1fr));gap:6px}
@media (max-width:600px){.wx-strip{grid-template-columns:repeat(auto-fill,minmax(68px,1fr))}}
.wx-hour{text-align:center;background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:8px 2px 7px;font-size:12px;line-height:1.5}
.wx-hour span{display:block}
.wx-h{font-weight:700;color:var(--muted)}
.wx-e{font-size:18px}
.wx-t{font-weight:700;font-size:14px}
.wx-p,.wx-w,.wx-hum{color:var(--muted);font-size:12px}
.wx-hour.wx-now{border-color:var(--accent);background:var(--accent-soft)}
.wx-hour.wx-now .wx-h{color:var(--accent)}
.inline-content .sub{color:var(--muted);font-size:14px}
.news-day{margin:0 0 8px}
.news-day h2{font-size:clamp(22px,3vw,26px)}
.news-day .count{color:var(--muted);font-size:15px;font-weight:400;font-family:var(--font-sans)}
.news-ed{font-size:17px;margin:18px 0 10px;color:var(--ink-soft)}
.news-item{background:var(--surface);border:1px solid var(--border);border-left:5px solid var(--accent);border-radius:var(--r-lg);box-shadow:var(--shadow-card);padding:16px 18px;margin:0 0 12px}
.news-item h4{margin:6px 0;font-size:18px;line-height:1.35;font-family:var(--font-serif)}
.news-item p{margin:6px 0;font-size:15px}
.news-item .links{margin:8px 0 0;font-size:14px}
.news-chip{display:inline-block;font-size:12px;font-weight:600;padding:3px 10px;border-radius:var(--r-pill);border:1.5px solid}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 4px}
.fchip{padding:11px 14px;border-radius:var(--r-pill);border:1px solid var(--border-strong);background:var(--surface);font-size:14px;cursor:pointer;touch-action:manipulation;font-family:var(--font-sans);color:var(--ink)}
.fchip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.fchip:hover{border-color:var(--accent)}
/* Лента с филтри (Събития + Новини): ред с бутон + търсене + „Изчисти“;
   панелът с чиповете се отваря САМО с бутона и скролва вътре в себе си */
.toolbar{background:rgba(255,255,255,.92);backdrop-filter:saturate(1.2) blur(10px);border:1px solid var(--border);border-radius:var(--r-lg);box-shadow:var(--shadow-card);padding:10px;max-width:1048px;width:calc(100% - 32px);margin:16px auto 4px;position:sticky;top:120px;z-index:40}
.tb-row{display:flex;gap:8px;align-items:center}
.tb-row input{flex:1;min-width:0;width:auto;padding:11px 16px;border:1px solid var(--border-strong);border-radius:var(--r-pill);font-size:16px;font-family:var(--font-sans);background:var(--surface);color:var(--ink)}
.tb-row input:focus{border-color:var(--accent);outline:none;box-shadow:0 0 0 3px var(--accent-soft)}
.toolbar .btn{padding:10px 14px;border-radius:var(--r-pill);border:1px solid var(--border-strong);background:var(--surface);font-size:14px;cursor:pointer;touch-action:manipulation;font-family:var(--font-sans);color:var(--ink);min-height:44px;white-space:nowrap}
.toolbar .btn:hover{border-color:var(--accent)}
.toolbar .btn.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.toolbar .filter-toggle{font-weight:700;display:inline-flex;align-items:center;gap:6px}
.toolbar.open .filter-toggle{background:var(--accent-soft);border-color:var(--accent)}
.tb-badge{display:inline-grid;place-items:center;min-width:22px;height:22px;padding:0 6px;border-radius:var(--r-pill);background:var(--accent);color:#fff;font-size:12px;font-weight:700}
.tb-badge[hidden],.tb-clear[hidden]{display:none}
.tb-clear{color:var(--accent-dark)!important;font-weight:600}
.tb-panel{display:none;max-height:min(62vh,560px,calc(100dvh - var(--stick,200px) - 16px));overflow:auto;overscroll-behavior:contain;padding:2px 2px 4px;margin-top:6px;border-top:1px solid var(--border)}
.toolbar.open .tb-panel{display:block}
.toolbar .label{font-size:12px;font-weight:700;color:var(--muted);margin:12px 4px 2px;display:block;text-transform:uppercase;letter-spacing:.05em}
.toolbar .chips{margin:4px 0}
/* всички дни избрани = нищо не е филтрирано: чиповете изглеждат неутрални */
.chips.all-on .fchip.on{background:var(--surface);color:var(--ink);border-color:var(--border-strong)}
.result-bar{max-width:1048px;width:calc(100% - 32px);margin:6px auto 0}
.result-bar .count-line{margin:4px 2px 0}
.result-bar .no-results{background:var(--surface);border:1px dashed var(--border-strong);border-radius:var(--r-lg);padding:18px;margin:10px 0;text-align:center}
main section,.ev-card,.news-item,.ev-day{scroll-margin-top:var(--stick,140px)}
@media (max-width:600px){.tb-clear-txt{display:none}.toolbar{padding:8px;width:calc(100% - 24px)}.toolbar .filter-toggle{padding:10px 12px}}
.ev-day{margin:0 0 6px}
.ev-day h2{font-size:clamp(22px,3vw,26px)}
.ev-day .count{color:var(--muted);font-size:15px;font-weight:400;font-family:var(--font-sans)}
.ev-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);box-shadow:var(--shadow-card);padding:16px 18px;margin:0 0 12px}
.ev-card h3{margin:4px 0 2px;font-size:18px;line-height:1.3}
.ev-time{font-weight:700;color:var(--accent);font-size:14px}
.ev-venue{color:var(--muted);font-size:14px;margin:2px 0 6px}
.ev-desc{font-size:15px;margin:6px 0}
.ev-desc summary{cursor:pointer;color:var(--accent);font-size:14px;padding:4px 0}
.ev-links{margin:8px 0 0;font-size:14px;display:flex;gap:16px;flex-wrap:wrap}
.ev-free{display:inline-block;background:#E8F5E9;color:#2E7D32;font-size:12px;font-weight:700;padding:3px 10px;border-radius:var(--r-pill)}
.ev-cat{display:inline-block;font-size:12px;font-weight:600;padding:3px 10px;border-radius:var(--r-pill);background:var(--surface-2);color:var(--ink-soft)}
.podari-map{overflow-x:auto}
.pv-table-wrap{overflow-x:auto}
.pv-table{width:100%;border-collapse:collapse;font-size:14px;min-width:620px}
.pv-table td,.pv-table th{padding:7px 8px;border-bottom:1px solid #eee;text-align:left;white-space:nowrap}
.pv-table th{color:#888;font-size:12px}
.sort-btn{background:none;border:0;padding:0;font:inherit;font-weight:700;color:#888;cursor:pointer;touch-action:manipulation;white-space:nowrap}
.sort-btn:hover{color:var(--accent)}
.sort-btn .sort-arrow{color:var(--accent);font-size:10px}
@media (max-width:600px){.podari-map svg{min-width:640px}}
.podari-note{font-size:13px;color:var(--muted)}
.pv-big{font-family:var(--font-serif);font-size:36px;line-height:1.1;color:var(--accent);font-weight:700;margin:0 0 4px}
.pv-step-n{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;background:var(--accent);color:#fff;font-weight:700;font-size:16px;margin-bottom:6px}
.pv-links{list-style:none;margin:0;padding:0}
.pv-links li{padding:7px 0;border-bottom:1px solid var(--border)}
.pv-links li:last-child{border-bottom:0}
.pv-links .pv-date{color:var(--muted);font-size:13px;margin-left:6px;white-space:nowrap}
.pv-amount{border:1px solid var(--border-strong);border-radius:var(--r-md);padding:10px 14px;background:var(--surface-2)}
.pv-amount b{font-size:18px;color:var(--accent)}
.pv-donate{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0}
.subnav{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px}
.subnav a{display:inline-block;padding:11px 14px;border:1px solid var(--border-strong);border-radius:var(--r-pill);background:var(--surface);font-size:14px;font-weight:600;color:var(--ink-soft);text-decoration:none;touch-action:manipulation}
.subnav a:hover{border-color:var(--accent);color:var(--accent)}
.fab-nav{position:fixed;right:18px;bottom:max(18px, env(safe-area-inset-bottom));z-index:60;width:54px;height:54px;border-radius:50%;border:0;background:linear-gradient(135deg,#D95B5B 0%,#D98A3D 25%,#3FA35C 50%,#2F80C9 75%,#7A5FD0 100%);color:#fff;font-size:26px;line-height:1;cursor:pointer;touch-action:manipulation;animation:fab-pulse 2.4s ease-out infinite}
@keyframes fab-pulse{0%{box-shadow:0 4px 16px rgba(122,95,208,.45),0 0 0 0 rgba(122,95,208,.45)}70%{box-shadow:0 4px 16px rgba(122,95,208,.45),0 0 0 14px rgba(122,95,208,0)}100%{box-shadow:0 4px 16px rgba(122,95,208,.45),0 0 0 0 rgba(122,95,208,0)}}
.fab-menu{position:fixed;right:18px;bottom:max(84px, calc(env(safe-area-inset-bottom) + 66px));z-index:60;width:min(300px,calc(100vw - 36px));max-height:min(60vh,420px);overflow-y:auto;background:var(--surface);border:1px solid var(--border-strong);border-radius:var(--r-md);box-shadow:var(--shadow-lift);padding:6px;display:none}
.fab-menu.open{display:block}
.fab-menu a{display:block;padding:11px 12px;border-radius:8px;color:var(--ink);text-decoration:none;font-weight:600;font-size:15px}
.fab-menu a:hover{background:var(--surface-2)}
.fab-menu .fab-title{padding:8px 12px 4px;color:var(--muted);font-size:13px;font-weight:700}
.tip{position:fixed;z-index:80;max-width:280px;background:#2B2620;color:#FBF9F3;padding:10px 12px;border-radius:10px;font-size:14px;line-height:1.45;box-shadow:0 8px 24px rgba(0,0,0,.25);pointer-events:none;display:none}
.tip.show{display:block}
.fab-menu a{border-left:3px solid transparent}
.fab-menu a.c1{color:#B04545;border-left-color:#B04545}
.fab-menu a.c2{color:#A66E1F;border-left-color:#A66E1F}
.fab-menu a.c3{color:#2F7D46;border-left-color:#2F7D46}
.fab-menu a.c4{color:#2F6BA8;border-left-color:#2F6BA8}
.fab-menu a.c5{color:#6A4FC0;border-left-color:#6A4FC0}
.subnav a.c1{color:#B04545;border-color:#B04545}
.subnav a.c2{color:#A66E1F;border-color:#A66E1F}
.subnav a.c3{color:#2F7D46;border-color:#2F7D46}
.subnav a.c4{color:#2F6BA8;border-color:#2F6BA8}
.subnav a.c5{color:#6A4FC0;border-color:#6A4FC0}
.fab-nav{overflow:hidden;font-weight:700;text-shadow:0 2px 4px rgba(0,0,0,.35),0 0 2px rgba(0,0,0,.2)}
.fab-nav::before{content:"";position:absolute;inset:0;border-radius:50%;background:linear-gradient(155deg,rgba(255,255,255,.9) 0%,rgba(255,255,255,.35) 22%,rgba(255,255,255,0) 42%)}
.fab-nav::after{content:"";position:absolute;inset:0;background:linear-gradient(115deg,transparent 20%,rgba(255,255,255,.75) 50%,transparent 80%);transform:translateX(-130%);animation:fab-shine 2.8s ease-in-out infinite}
@keyframes fab-shine{0%,45%{transform:translateX(-130%)}75%,100%{transform:translateX(130%)}}
@media (max-width:600px){.fab-nav{right:12px;bottom:max(12px, env(safe-area-inset-bottom))}.fab-menu{right:12px;bottom:max(78px, calc(env(safe-area-inset-bottom) + 66px))}}
.sw{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:3px;vertical-align:-1px}
.dist{width:100%;border-collapse:collapse;font-size:14px;margin:6px 0}
.dist td,.dist th{padding:4px 6px;border-bottom:1px solid var(--border);text-align:left}
.dist th{color:var(--muted);font-size:12px}
@media (min-width:900px){
  .nav-inner{flex-wrap:wrap;justify-content:center;overflow:visible}
}
/* по-спокоен, съвременен вид: бутонът със секциите е в акцентния цвят, без дъга и пулсиране */
.fab-nav{background:var(--accent);animation:none;box-shadow:0 6px 20px rgba(156,73,61,.35);text-shadow:none}
.fab-nav::before,.fab-nav::after{display:none}
.fab-nav:hover{background:var(--accent-dark)}
.card,.news-item,.ev-card{transition:box-shadow .2s ease,transform .2s ease}
.card:hover,.news-item:hover,.ev-card:hover{transform:translateY(-1px);box-shadow:var(--shadow-lift)}
.nav a:hover{color:var(--ink);background:var(--surface-2)}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
"""

JS = """
// Менюто се скролва до активната страница (центрира я в лентата)
(function(){
  var nav = document.querySelector('.nav-inner');
  var cur = nav && nav.querySelector('a[aria-current="page"]');
  if (nav && cur) {
    var r = cur.getBoundingClientRect(), n = nav.getBoundingClientRect();
    nav.scrollLeft += (r.left + r.width / 2) - (n.left + n.width / 2);
  }
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
// Търсене на страницата (архив и единични страници): филтрира картите по data-search.
// Страниците Събития и Новини имат собствен единен филтър (виж по-долу) — тук се пропускат.
(function(){
  var q = document.getElementById('q');
  if (!q) return;
  if (document.getElementById('evFilters') || document.getElementById('newsFilters')) return;
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
// Времето: маркира текущия час за днешния ден
(function(){
  var now = new Date();
  var iso = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
  var cell = document.querySelector('.wx-hour[data-date="' + iso + '"][data-hour="' + now.getHours() + '"]');
  if (cell) { cell.classList.add('wx-now'); cell.scrollIntoView({block: 'nearest', inline: 'center'}); }
})();
// Новини: ЕДИНЕН филтър — търсене + категория + ден, комбинирани
// (преди търсенето и категорията се презаписваха взаимно)
(function(){
  var tb = document.getElementById('newsFilters');
  if (!tb) return;
  var q = document.getElementById('q');
  var countEl = document.getElementById('count');
  var noRes = document.getElementById('no-results');
  var cat = 'all';
  var dayChips = tb.querySelectorAll('#newsDayChips .fchip[data-day]:not([data-day="all"])');
  var dayTotal = dayChips.length;
  var activeDays = new Set();
  dayChips.forEach(function(b){ activeDays.add(b.dataset.day); });
  function apply(){
    var needle = (q.value || '').trim().toLowerCase();
    var visible = 0, total = 0;
    document.querySelectorAll('.news-item').forEach(function(c){
      total++;
      var okQ = !needle || c.dataset.search.toLowerCase().indexOf(needle) !== -1;
      var okCat = cat === 'all' || c.dataset.cat === cat;
      var okDay = activeDays.has(c.dataset.day);
      var hit = okQ && okCat && okDay;
      c.hidden = !hit;
      if (hit) visible++;
    });
    document.querySelectorAll('.news-ed-group').forEach(function(g){
      var any = false;
      g.querySelectorAll('.news-item').forEach(function(c){ if (!c.hidden) any = true; });
      g.hidden = !any;
    });
    document.querySelectorAll('.news-day').forEach(function(s){
      var vis = 0;
      s.querySelectorAll('.news-item').forEach(function(c){ if (!c.hidden) vis++; });
      s.hidden = vis === 0;
      var sp = s.querySelector('h2 .count');
      if (sp) sp.textContent = '· ' + vis + ' новини';
    });
    var filtered = needle || cat !== 'all' || activeDays.size !== dayTotal;
    if (countEl) countEl.textContent = filtered ? ('Показани: ' + visible + ' от ' + total) : '';
    if (noRes) noRes.hidden = visible > 0;
    var dc = document.getElementById('newsDayChips');
    if (dc) dc.classList.toggle('all-on', activeDays.size === dayTotal);
    syncToolbar(tb);
  }
  var tgl = document.getElementById('newsFilterToggle');
  // Панелът се отваря и затваря САМО с бутона (без автоматично свиване при скрол)
  setupToolbar(tb, tgl, function(){
    q.value = '';
    cat = 'all';
    tb.querySelectorAll('#catChips .fchip').forEach(function(x){ x.classList.toggle('on', x.dataset.cat === 'all'); });
    setDays(function(){ return true; });
  }, function(){
    return ((q.value || '').trim() ? 1 : 0) + (cat !== 'all' ? 1 : 0) + (activeDays.size !== dayTotal ? 1 : 0);
  });
  tb.querySelectorAll('#catChips .fchip').forEach(function(b){
    b.addEventListener('click', function(){
      tb.querySelectorAll('#catChips .fchip').forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on'); cat = b.dataset.cat; apply();
    });
  });
  // Дни: кликът ИЗБИРА дни — могат да се избират няколко наведнъж (един ден,
  // два дни, всички). Когато всички са избрани, клик изолира само този ден;
  // следващ клик върху друг ден го ДОБАВЯ към избора; клик върху избран ден
  // го маха. „Всички дни" връща всички. Ако се махне последният избран ден,
  // се връщат всички дни (празен избор не показва нищо).
  function setDays(pred){
    var all = true;
    tb.querySelectorAll('#newsDayChips .fchip').forEach(function(b){
      if (b.dataset.day === 'all') return;
      var on = pred(b.dataset.day);
      b.classList.toggle('on', on);
      if (on) activeDays.add(b.dataset.day); else activeDays.delete(b.dataset.day);
      if (!on) all = false;
    });
    var allBtn = tb.querySelector('#newsDayChips .fchip[data-day="all"]');
    if (allBtn) allBtn.classList.toggle('on', all);
    apply();
  }
  tb.querySelectorAll('#newsDayChips .fchip').forEach(function(b){
    b.addEventListener('click', function(){
      var d = b.dataset.day;
      if (d === 'all') { setDays(function(){ return true; }); return; }
      if (activeDays.size === dayTotal) {
        // Всички са избрани — клик изолира само този ден. Проверката за
        // „всички избрани" е ПЪРВА: has(d) преди нея прави изолирането
        // недостижимо (при всички избрани has(d) винаги е вярно).
        setDays(function(x){ return x === d; }); return;
      }
      if (activeDays.has(d)) {
        activeDays.delete(d); b.classList.remove('on');
        if (activeDays.size === 0) { setDays(function(){ return true; }); return; }
      } else {
        activeDays.add(d); b.classList.add('on');
      }
      var allBtn = tb.querySelector('#newsDayChips .fchip[data-day="all"]');
      if (allBtn) allBtn.classList.toggle('on', activeDays.size === dayTotal);
      apply();
    });
  });
  var todayBtn = document.getElementById('newsToday');
  if (todayBtn) todayBtn.addEventListener('click', function(){
    var d = new Date();
    var dd = String(d.getDate()).padStart(2, '0') + '.' + String(d.getMonth() + 1).padStart(2, '0');
    var found = false;
    tb.querySelectorAll('#newsDayChips .fchip').forEach(function(x){ if (x.dataset.day === dd) found = true; });
    if (found) setDays(function(x){ return x === dd; });
  });
  q.addEventListener('input', apply);
})();
// Събития: ЕДИНЕН филтър — търсене + ден (няколко) + категория + източник +
// разстояние + само безплатни / само нови / само с посочен час + Днес / Този уикенд
(function(){
  var tb = document.getElementById('evFilters');
  if (!tb) return;
  var q = document.getElementById('q');
  var countEl = document.getElementById('count');
  var noRes = document.getElementById('no-results');
  var cat = '', src = '', dist = '';
  var freeOnly = false, newOnly = false, timeOnly = false;
  var activeDays = new Set();
  tb.querySelectorAll('#evDayChips .fchip').forEach(function(b){ activeDays.add(b.dataset.day); });
  function anyFilter(){
    return (q.value || '').trim() !== '' || cat !== '' || src !== '' || dist !== '' ||
      freeOnly || newOnly || timeOnly || activeDays.size !== tb.querySelectorAll('#evDayChips .fchip').length;
  }
  function apply(){
    var needle = (q.value || '').trim().toLowerCase();
    var visible = 0, total = 0;
    document.querySelectorAll('.ev-card').forEach(function(c){
      total++;
      var okQ = !needle || c.dataset.search.toLowerCase().indexOf(needle) !== -1;
      var okCat = !cat || c.dataset.cat === cat;
      var okSrc = !src || c.dataset.src === src;
      var okDist = !dist || (dist === 'far' ? c.dataset.far === '1' : c.dataset.far === '0');
      var okFree = !freeOnly || c.dataset.free === '1';
      var okNew = !newOnly || c.dataset.new === '1';
      var okTime = !timeOnly || c.dataset.time === '1';
      var okDay = activeDays.has(c.dataset.day);
      var hit = okQ && okCat && okSrc && okDist && okFree && okNew && okTime && okDay;
      c.hidden = !hit;
      if (hit) visible++;
    });
    document.querySelectorAll('.ev-day').forEach(function(s){
      var vis = 0;
      s.querySelectorAll('.ev-card').forEach(function(c){ if (!c.hidden) vis++; });
      s.hidden = vis === 0;
      var sp = s.querySelector('h2 .count');
      if (sp) sp.textContent = '· ' + vis + ' събития';
    });
    if (countEl) countEl.textContent = anyFilter() ? ('Показани: ' + visible + ' от ' + total + ' събития') : '';
    if (noRes) noRes.hidden = visible > 0;
    var dc = document.getElementById('evDayChips');
    if (dc) dc.classList.toggle('all-on', activeDays.size === dc.querySelectorAll('.fchip').length);
    syncToolbar(tb);
  }
  var tgl = document.getElementById('evFilterToggle');
  // Панелът се отваря и затваря САМО с бутона (без автоматично свиване при скрол)
  setupToolbar(tb, tgl, function(){
    q.value = ''; cat = ''; src = ''; dist = '';
    freeOnly = false; newOnly = false; timeOnly = false;
    ['#evCatChips', '#evSrcChips', '#evDistChips'].forEach(function(sel){
      tb.querySelectorAll(sel + ' .fchip').forEach(function(x, i){ x.classList.toggle('on', i === 0); });
    });
    ['evFreeBtn', 'evNewBtn', 'evTimeBtn'].forEach(function(id){ var b = document.getElementById(id); if (b) b.classList.remove('on'); });
    setDays(function(){ return true; });
  }, function(){
    return ((q.value || '').trim() ? 1 : 0) + (cat ? 1 : 0) + (src ? 1 : 0) + (dist ? 1 : 0) +
      (freeOnly ? 1 : 0) + (newOnly ? 1 : 0) + (timeOnly ? 1 : 0) +
      (activeDays.size !== tb.querySelectorAll('#evDayChips .fchip').length ? 1 : 0);
  });
  tb.querySelectorAll('#evCatChips .fchip').forEach(function(b){
    b.addEventListener('click', function(){
      tb.querySelectorAll('#evCatChips .fchip').forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on'); cat = b.dataset.cat || ''; apply();
    });
  });
  tb.querySelectorAll('#evSrcChips .fchip').forEach(function(b){
    b.addEventListener('click', function(){
      tb.querySelectorAll('#evSrcChips .fchip').forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on'); src = b.dataset.src || ''; apply();
    });
  });
  tb.querySelectorAll('#evDistChips .fchip').forEach(function(b){
    b.addEventListener('click', function(){
      tb.querySelectorAll('#evDistChips .fchip').forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on'); dist = b.dataset.dist || ''; apply();
    });
  });
  function toggleBtn(id, get, set){
    var b = document.getElementById(id);
    if (!b) return;
    b.addEventListener('click', function(){ var v = !get(); set(v); b.classList.toggle('on', v); apply(); });
  }
  toggleBtn('evFreeBtn', function(){ return freeOnly; }, function(v){ freeOnly = v; });
  toggleBtn('evNewBtn', function(){ return newOnly; }, function(v){ newOnly = v; });
  toggleBtn('evTimeBtn', function(){ return timeOnly; }, function(v){ timeOnly = v; });
  // Дни: кликът ИЗБИРА дни — могат да се избират няколко наведнъж (един ден,
  // два дни, всички). Когато всички са избрани, клик изолира само този ден;
  // следващ клик върху друг ден го ДОБАВЯ към избора; клик върху избран ден
  // го маха. Ако се махне последният избран ден, се връщат всички дни.
  tb.querySelectorAll('#evDayChips .fchip').forEach(function(b){
    b.addEventListener('click', function(){
      var d = b.dataset.day;
      if (activeDays.size === tb.querySelectorAll('#evDayChips .fchip').length) {
        // Всички са избрани — клик изолира само този ден. Проверката за
        // „всички избрани" е ПЪРВА: has(d) преди нея прави изолирането
        // недостижимо (при всички избрани has(d) винаги е вярно).
        setDays(function(x){ return x === d; }); return;
      }
      if (activeDays.has(d)) {
        activeDays.delete(d); b.classList.remove('on');
        if (activeDays.size === 0) { setDays(function(){ return true; }); return; }
      } else {
        activeDays.add(d); b.classList.add('on');
      }
      apply();
    });
  });
  function setDays(pred){
    tb.querySelectorAll('#evDayChips .fchip').forEach(function(b){
      var on = pred(b.dataset.day);
      b.classList.toggle('on', on);
      if (on) activeDays.add(b.dataset.day); else activeDays.delete(b.dataset.day);
    });
    apply();
  }
  var allBtn = document.getElementById('evAllDays');
  if (allBtn) allBtn.addEventListener('click', function(){ setDays(function(){ return true; }); });
  var weBtn = document.getElementById('evWeekend');
  if (weBtn) weBtn.addEventListener('click', function(){
    setDays(function(iso){ var g = new Date(iso + 'T12:00:00').getDay(); return g === 0 || g === 6; });
  });
  var todayBtn = document.getElementById('evToday');
  if (todayBtn) todayBtn.addEventListener('click', function(){
    var d = new Date();
    var iso = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    if (!tb.querySelector('#evDayChips .fchip[data-day="' + iso + '"]')) {
      if (countEl) countEl.textContent = 'Днес няма събития в списъка.';
      return;
    }
    setDays(function(x){ return x === iso; });
  });
  q.addEventListener('input', apply);
})();
// Плаваща стрелка вдясно: меню с разделите на текущата страница
(function(){
  var btn = document.getElementById('fabNav');
  var menu = document.getElementById('fabMenu');
  if (!btn || !menu) return;
  var heads = document.querySelectorAll('main h2');
  if (heads.length < 2) { btn.style.display = 'none'; return; }
  function safeFragId(id){
    if (typeof id !== 'string' || !id || !/^[\\w.-]+$/.test(id)) return null;
    return id;
  }
  function appendFabLink(parent, href, text, cls, tip){
    var a = document.createElement('a');
    if (cls) a.className = cls;
    a.href = href;
    a.textContent = text;
    if (tip) a.setAttribute('data-tip', tip);
    parent.appendChild(a);
  }
  menu.replaceChildren();
  var fabTitle = document.createElement('div');
  fabTitle.className = 'fab-title';
  fabTitle.textContent = 'Раздели на тази страница';
  menu.appendChild(fabTitle);
  appendFabLink(menu, '#top', '⬆ Начало на страницата', '', 'Връща те най-горе на страницата.');
  var SEC_COLORS = {'podari-list':'c1','pv-nearest':'c2','pv-near-sofia':'c5','pv-map':'c3','pv-mission':'c4','pv-join':'c5',
    'pv-academy':'c1','pv-work':'c2','pv-docs':'c3','pv-stories':'c4','pv-media':'c5',
    'pv-podcast':'c1','pv-support':'c2','pv-contacts':'c3'};
  var TIPS = {'podari-list':'Предстоящи посещения при деца в домове — избери дата и се запиши.',
    'pv-nearest':'Трите най-близки по време посещения — най-бързият път да се включиш.',
    'pv-near-sofia':'Посещения, подредени по разстояние от София — най-близките първи, с час на тръгване и линк за записване.',
    'pv-map':'Карта на България с всички места и разстоянията от София.',
    'pv-mission':'Фондацията в числа — 16 години, 500 доброволци, 400 деца, 18 институции.',
    'pv-join':'Пет стъпки до първото посещение и петте правила на доброволеца.',
    'pv-academy':'Безплатни уроци за децата — Буквар, Диплома и Алма Матер, по 15 евро на час.',
    'pv-work':'Шестдневна програма за младежи от домове — как се търси работа и се живее самостоятелно.',
    'pv-docs':'Наръчник, декларации и документи за доброволци — за сваляне.',
    'pv-stories':'Истории от блога на фондацията — какво се случва по посещенията.',
    'pv-media':'Репортажи и статии за Подари Време в медиите.',
    'pv-podcast':'Подкаст „Подарени истории" и бюлетин „Доброволчески вести".',
    'pv-support':'Дари — 15 евро са 20 км път, 30 евро са урок за две деца, 50 евро са половината път до Враца за 15 доброволци.',
    'pv-contacts':'Телефон, имейл и адрес на фондацията.'};
  var TIPS_BY_TEXT = {'Днес накратко':'Времето днес и следващото събитие.',
    'Тази седмица':'Брой събития за всеки ден от седмицата — натисни деня, за да видиш събитията.'};
  heads.forEach(function(h, i){
    if (!h.id) h.id = 'sec-' + (i + 1);
    var t = (h.textContent || '').replace(/\\s+/g, ' ').trim();
    if (!t) return;
    var sec = h.closest ? h.closest('section') : null;
    var sid = sec ? sec.id : '';
    var target = safeFragId(sid) || safeFragId(h.id);
    if (!target) return;
    var isDay = sid.indexOf('day-') === 0 || sid.indexOf('pday-') === 0;
    var cls = SEC_COLORS[sid] || (isDay ? 'c3' : 'c' + ((i % 5) + 1));
    var tip = TIPS[sid] || TIPS_BY_TEXT[t] || (isDay ? (document.getElementById('podari-list') ? 'Всички посещения на тази дата — натисни, за да отидеш на деня.' : 'Всичко за този ден — натисни, за да отидеш на деня.') : '');
    appendFabLink(menu, '#' + target, t, cls, tip || null);
  });
  btn.addEventListener('click', function(e){
    e.stopPropagation();
    menu.classList.toggle('open');
  });
  menu.addEventListener('click', function(e){
    if (e.target.tagName === 'A') menu.classList.remove('open');
  });
  document.addEventListener('click', function(e){
    if (!menu.contains(e.target) && e.target !== btn) menu.classList.remove('open');
  });
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape') menu.classList.remove('open');
  });
})();
// Popup обяснение при hover върху елементи с data-tip
(function(){
  var tip = document.getElementById('tip');
  if (!tip) return;
  var timer = null, current = null;
  function show(el){
    tip.textContent = el.getAttribute('data-tip');
    tip.classList.add('show');
    var r = el.getBoundingClientRect();
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2));
    var top = r.top - h - 8;
    if (top < 8) top = r.bottom + 8;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }
  function hide(){
    tip.classList.remove('show');
    current = null;
    if (timer) { clearTimeout(timer); timer = null; }
  }
  document.addEventListener('mouseover', function(e){
    var el = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
    if (!el) { hide(); return; }
    if (current === el) return;
    current = el;
    if (timer) clearTimeout(timer);
    timer = setTimeout(function(){ show(el); }, 200);
  });
  document.addEventListener('mouseout', function(e){
    var el = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
    if (el && (!e.relatedTarget || !el.contains(e.relatedTarget))) hide();
  });
  document.addEventListener('focusin', function(e){
    var el = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
    if (el) { current = el; show(el); }
  });
  document.addEventListener('focusout', function(){ hide(); });
  document.addEventListener('click', function(e){
    var el = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
    if (el) hide();
  });
})();

// Общи помощници за лентата с филтри (Новини, Събития)
function setupToolbar(tb, tgl, resetFn, countFn){
  var open = false;
  function render(){
    tb.classList.toggle('open', open);
    if (tgl) tgl.setAttribute('aria-expanded', String(open));
  }
  if (tgl) tgl.addEventListener('click', function(){ open = !open; render(); });
  render();
  var clr = tb.querySelector('.tb-clear');
  if (clr) clr.addEventListener('click', function(){
    resetFn();
    var q = tb.querySelector('input[type="search"]');
    if (q) q.dispatchEvent(new Event('input'));
    if (q) q.focus(); else if (tgl) tgl.focus();
  });
  tb._count = countFn;
  function stick(){
    var h = document.querySelector('.site-header');
    var hh = h ? h.getBoundingClientRect().height : 0;
    tb.style.top = (hh + 8) + 'px';
    var row = tb.querySelector('.tb-row');
    var rh = row ? row.getBoundingClientRect().height : 48;
    document.documentElement.style.setProperty('--stick', Math.round(hh + rh + 44) + 'px');
  }
  stick();
  window.addEventListener('resize', stick);
  syncToolbar(tb);
}
function syncToolbar(tb){
  tb.querySelectorAll('.tb-panel .fchip, .tb-panel .btn').forEach(function(b){
    b.setAttribute('aria-pressed', String(b.classList.contains('on')));
  });
  if (!tb._count) return;
  var n = tb._count();
  var badge = tb.querySelector('.tb-badge');
  if (badge) { badge.textContent = String(n); badge.hidden = n === 0; }
  var clr = tb.querySelector('.tb-clear');
  if (clr) clr.hidden = n === 0;
}
"""

SEARCH_JS = """
(function(){
  var q = document.getElementById('q');
  var results = document.getElementById('results');
  var countEl = document.getElementById('count');
  var data = null;
  function showStatus(msg){
    results.replaceChildren();
    var p = document.createElement('p');
    p.className = 'no-results';
    p.textContent = msg;
    results.appendChild(p);
  }
  function safeResultHref(u){
    if (typeof u !== 'string') return null;
    u = u.trim();
    if (!u || /[\\s<>"'`]/.test(u)) return null;
    var lower = u.toLowerCase();
    if (lower.indexOf('javascript:') === 0 || lower.indexOf('data:') === 0 ||
        lower.indexOf('vbscript:') === 0 || lower.indexOf('file:') === 0) return null;
    if (/^[a-z][a-z0-9+.-]*:/i.test(u)) return null;
    if (!/^([\\w%./-]+\\.html(?:#[\\w%./-]+)?|#[\\w%./-]+)$/.test(u)) return null;
    return u;
  }
  function appendResultCard(entry){
    var card = document.createElement('article');
    card.className = 'result-card';
    var h3 = document.createElement('h3');
    var a = document.createElement('a');
    var href = safeResultHref(entry.u);
    if (href) a.href = href;
    else { a.href = '#'; a.setAttribute('aria-disabled', 'true'); }
    a.textContent = entry.t || '';
    h3.appendChild(a);
    card.appendChild(h3);
    var meta = document.createElement('p');
    meta.className = 'meta';
    var metaText = entry.k || '';
    if (entry.d) metaText += (metaText ? ' · ' : '') + entry.d;
    meta.textContent = metaText;
    card.appendChild(meta);
    if (entry.s) {
      var body = document.createElement('p');
      body.textContent = entry.s;
      card.appendChild(body);
    }
    return card;
  }
  function render(needle){
    needle = (needle || '').trim().toLowerCase();
    if (!data) { showStatus('Зареждам индекса…'); return; }
    if (!needle) {
      showStatus('Напиши дума — търси в изданията и събитията.');
      countEl.textContent = '';
      return;
    }
    var all = data.filter(function(e){
      return (e.t + ' ' + e.s + ' ' + e.k).toLowerCase().indexOf(needle) !== -1;
    });
    var hits = all.slice(0, 40);
    countEl.textContent = all.length > hits.length ? ('Показани: ' + hits.length + ' от ' + all.length + ' — уточни търсенето') : ('Намерени: ' + all.length);
    if (!hits.length) {
      showStatus('Няма съвпадения — опитай с по-кратка дума.');
      return;
    }
    results.replaceChildren();
    hits.forEach(function(e){ results.appendChild(appendResultCard(e)); });
  }
  fetch('search.json').then(function(r){ return r.json(); }).then(function(j){
    data = j; render(q.value);
  }).catch(function(){
    showStatus('Индексът не се зареди — опитай отново след малко.');
  });
  q.addEventListener('input', function(){ render(q.value); });
  var params = new URLSearchParams(location.search);
  if (params.get('q')) { q.value = params.get('q'); }
  render(q.value);
})();
"""

PODARI_JS = r"""
(function(){
  var q = document.getElementById('podari-q');
  var countEl = document.getElementById('podari-count');
  var cat = 'all';
  function render(){
    var needle = (q.value || '').trim().toLowerCase();
    var total = 0;
    document.querySelectorAll('#podari-list .ev-card').forEach(function(c){
      var hit = (cat === 'all' || c.dataset.kind === cat)
        && (!needle || c.dataset.search.toLowerCase().indexOf(needle) !== -1);
      c.hidden = !hit;
      if (hit) total++;
    });
    document.querySelectorAll('#podari-list .ev-day').forEach(function(s){
      var any = false;
      s.querySelectorAll('.ev-card').forEach(function(c){ if (!c.hidden) any = true; });
      s.hidden = !any;
    });
    if (countEl) countEl.textContent = total ? ('Предстоящи: ' + total) : '';
  }
  q.addEventListener('input', render);
  document.querySelectorAll('#podariChips .fchip').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('#podariChips .fchip').forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on');
      cat = b.dataset.cat;
      render();
    });
  });
  render();
})();
// Таблица „Списък по близост до София": сортиране по колони — дата,
// разстояние (км) или час на тръгване. Първи клик върху колона = нарастващо,
// втори клик = намаляващо; стрелката показва активната колона и посоката.
(function(){
  var tbl = document.getElementById('pvNearTable');
  if (!tbl) return;
  var tbody = tbl.querySelector('tbody');
  if (!tbody) return;
  var CHAINS = {
    date: ['date', 'dep', 'place'],
    km: ['km', 'date', 'dep'],
    dep: ['dep', 'date', 'place']
  };
  var activeKey = 'date';
  function cmpVal(a, b, key){
    var va = a.dataset[key] || '', vb = b.dataset[key] || '';
    // Числово сравнение САМО при изцяло числови стойности — parseFloat върху
    // дата като "2026-11-28" връща 2026 и всички дати от една година стават равни.
    var num = /^-?\d+(\.\d+)?$/;
    if (num.test(va) && num.test(vb)) return parseFloat(va) - parseFloat(vb);
    return va < vb ? -1 : va > vb ? 1 : 0;
  }
  function sortBy(key, dir){
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    var chain = CHAINS[key] || [key];
    rows.sort(function(a, b){
      var c = 0;
      for (var i = 0; i < chain.length && c === 0; i++) c = cmpVal(a, b, chain[i]);
      return dir === 'desc' ? -c : c;
    });
    rows.forEach(function(r){ tbody.appendChild(r); });
  }
  tbl.querySelectorAll('th .sort-btn').forEach(function(btn){
    btn.addEventListener('click', function(){
      var key = btn.dataset.sort;
      var dir = (key === activeKey && btn.dataset.dir === 'asc') ? 'desc' : 'asc';
      activeKey = key;
      tbl.querySelectorAll('th .sort-btn').forEach(function(x){
        x.dataset.dir = 'asc';
        var ar = x.querySelector('.sort-arrow');
        if (ar) ar.textContent = '';
      });
      btn.dataset.dir = dir;
      var ar = btn.querySelector('.sort-arrow');
      if (ar) ar.textContent = dir === 'asc' ? '▲' : '▼';
      sortBy(key, dir);
    });
  });
})();
"""





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
        '<a class="btn-primary" href="news.html#day-%s">Чети новините ↓</a>'
        '</article>'
        % (item["part"], esc(search), emoji, label, date_str, weekday_bg(item["date"]),
           count, bullets, item["date"].strftime("%d-%m"))
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
    if not news_items:
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<rss version="2.0"><channel>'
                '<title>Събития в София — Новини</title>'
                '<link>%s</link>'
                '<description>Новини сутрин, следобед и вечер — автоматичен обзор</description>'
                '<language>bg</language></channel></rss>' % BASE_URL)
    max_date = max(i["date"] for i in news_items)
    recent = [i for i in news_items if (max_date - i["date"]).days <= 2]
    for item in sorted(recent, key=lambda x: (x["date"], PART_ORDER[x["part"]]),
                       reverse=True)[:20]:
        count = count_articles(read_file(item["name"]))
        title = "Новини %s — %s" % (fmt_date(item["date"]), PART_LABEL[item["part"]])
        pub = formatdate(file_mtime(item["name"]), usegmt=True)
        ed_id = "%s-%s" % (item["date"].strftime("%d-%m"), item["part"])
        items.append(
            "<item><title>%s</title><link>%snews.html#ed-%s</link>"
            "<pubDate>%s</pubDate><description>%d новини</description></item>"
            % (esc(title), BASE_URL, ed_id, pub, count)
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        '<title>Събития в София — Новини</title>'
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
    # RADAR, Коли и AI план са СКРИТИ от публичния сайт (25.11.2026, по искане
    # на Philippe — лична информация); източниците им остават локално и
    # не се качват в репото.
    # Подари Време е свалено изцяло от сайта на 25.11.2026 (също по негово
    # искане); кодът за страницата е запазен, но вече не се изпълнява.
    single_defs = [
        ("vreme", "Времето", "Времето в София", "Прогноза за следващите дни.",
         "weather.html", "🌤️"),
        ("assistants", "AI асистенти", "AI асистенти: радар",
         "43 лични AI асистенти — кои работят от България, цени и източници.",
         "assistants-content.html", "🤖"),
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

    # v3: събития от регистъра (от днес нататък) + статии от най-новото издание
    registry = load_events_registry()
    registry_missing = registry is None
    registry = registry or []
    today_iso = now.strftime("%Y-%m-%d")
    upcoming = []
    for e in registry:
        if e.get("status", "active") != "active":
            continue
        if e.get("date", "") < today_iso:
            continue
        upcoming.append(e)
    upcoming.sort(key=lambda e: (e.get("date", ""), e.get("start") or "99:99",
                                 e.get("name", "")))
    free_count = sum(1 for e in upcoming if e.get("free"))
    articles = []
    if news:
        articles = parse_news_articles(texts[news[-1]["name"]])
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
            '<title>' + esc(title) + ' — Събития в София</title>\n'
            '<meta name="description" content="Новини, събития и справки — обновява се автоматично.">\n'
            '<meta name="theme-color" content="#FBF9F3">\n'
            '<meta name="referrer" content="strict-origin-when-cross-origin">\n'
            '<meta http-equiv="Content-Security-Policy" content="'
            "default-src 'self'; base-uri 'self'; form-action 'self'; "
            "object-src 'none'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; frame-src 'self'\">\n"
            '<link rel="icon" href="favicon.ico" sizes="any">\n'
            '<link rel="icon" href="favicon.svg" type="image/svg+xml">\n'
            '<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">\n'
            '<link rel="apple-touch-icon" href="apple-touch-icon.png">\n'
            '<link rel="manifest" href="site.webmanifest">\n'
            '<link rel="alternate" type="application/rss+xml" title="Събития в София — Новини" href="feed.xml">\n'
            '<style>' + CSS + '</style>\n</head>\n<body>\n'
            '<a class="skip-link" href="#main">Към съдържанието</a>\n'
            '<header class="site-header"><div class="container">'
            '<div class="header-row"><a class="brand" href="index.html">'
            '<img src="favicon.svg" alt="" width="32" height="32">'
            '<span class="brand-name">Събития в София</span></a>'
            '<span class="brand-date">' + esc(today_str) + '</span></div>'
            '<nav class="nav" aria-label="Раздели"><div class="nav-inner">' + nav_html(active) + '</div></nav>'
            '</div></header>\n'
            '<main id="main">' + body_html + '</main>\n'
            '<footer><div class="container">'
            '<div class="foot-nav">' + nav_html(active) + '</div>'
            '<p>Последно обновяване: ' + esc(updated) + ' · Обновява се автоматично на всеки час.</p>'
            '<p><a href="feed.xml">RSS емисия — новините</a> · <a href="#top">Нагоре ↑</a></p>'
            '</div></footer>\n'
            '<button id="fabNav" class="fab-nav" type="button" aria-label="Раздели на страницата" title="Раздели на страницата">↑</button>\n'
            '<nav id="fabMenu" class="fab-menu" aria-label="Раздели на страницата"></nav>\n'
            '<div id="tip" class="tip" role="tooltip"></div>\n'
            '<script>' + JS + '</script>\n' + extra_js +
            '</body>\n</html>\n'
        )
        return page

    def write_page(filename, content):
        if filename == "events.html" and registry_missing and os.path.exists(os.path.join(SITE_DIR, filename)):
            return os.path.getsize(os.path.join(SITE_DIR, filename))
        with open(os.path.join(SITE_DIR, filename), "w", encoding="utf-8") as f:
            f.write(content)
        return len(content.encode("utf-8"))

    sizes = {}

    # ================= НАЧАЛО =================
    if news:
        latest = news[-1]
        latest_text = texts[latest["name"]]
        hero_html = (
            '<div class="container" id="top"><div class="hero"><div class="hero-text">'
            '<p class="kicker">Най-новото</p>'
            '<h1>Новини <span class="hl">%s, %s</span> — <em>%s</em></h1>'
            '<p class="lede">%d новини · %s</p><ul>%s</ul>'
            '<a class="btn-primary" href="news.html">Чети новините ↓</a></div>'
            '<div class="hero-art" aria-hidden="true">'
            '<svg viewBox="0 0 320 180" role="img" aria-label="Витоша със слънце">'
            '<circle cx="252" cy="42" r="20" fill="#9C493D"/>'
            '<path d="M40 52 q6 -6 12 0 q6 -6 12 0" stroke="#6B5F4D" fill="none" stroke-width="2" stroke-linecap="round"/>'
            '<path d="M84 38 q5 -5 10 0 q5 -5 10 0" stroke="#6B5F4D" fill="none" stroke-width="2" stroke-linecap="round"/>'
            '<polygon points="0,180 60,90 120,140 180,70 240,130 320,80 320,180" fill="#6B5F4D"/>'
            '<polygon points="0,180 40,120 100,160 160,100 220,150 280,110 320,150 320,180" fill="#2B2620"/>'
            '<rect x="158" y="70" width="4" height="32" fill="#2B2620"/>'
            '<rect x="151" y="70" width="18" height="3" fill="#2B2620"/>'
            '</svg></div></div></div>'
            % (fmt_date(latest["date"]), weekday_bg(latest["date"]),
               PART_LABEL[latest["part"]],
               count_articles(latest_text), PART_EMOJI[latest["part"]],
               "".join("<li>%s</li>" % esc(t) for t in extract_h4_titles(latest_text, 3)))
        )
        latest_date = latest["date"]
        today_items = [i for i in news if i["date"] == latest_date]
        today_cards = "".join(news_preview_card(i, texts[i["name"]]) for i in today_items)
    else:
        hero_html = '<div class="container" id="top"></div>'
        today_cards = ""

    # събития от днес нататък — карта за началната
    events_card = ""
    if upcoming:
        last_iso = upcoming[-1]["date"]
        events_card = (
            '<article class="card"><span class="icon">🗓️</span>'
            '<h3>Събития — от днес нататък</h3>'
            '<p class="meta">%d събития · 🆓 %d безплатни · до %s</p>'
            '<a class="btn-primary" href="events.html">Виж събитията ↓</a></article>'
            % (len(upcoming), free_count,
               fmt_date(datetime.strptime(last_iso, "%Y-%m-%d")))
        )

    # „Днес накратко" — време и следващо събитие
    glance_cards = []
    wx_path = os.path.join(SITE_DIR, "weather.html")
    if os.path.exists(wx_path):
        wx_html = read_file("weather.html")
        m = re.search(r'<section class="wx-day">.*?<span class="wx-dow">(.*?)</span>'
                      r'.*?<div class="wx-sum">(.*?)</div>', wx_html, re.S)
        if m:
            cond = m.group(1).split("·")[-1].strip()
            mm = re.search(r"([+-]?\d+)° / ([+-]?\d+)°", m.group(2))
            big = "%s° / %s°" % (mm.group(1), mm.group(2)) if mm else "—"
            parts = [p.strip() for p in m.group(2).split("·")]
            parts = [p for p in parts if not re.search(r"[+-]?\d+° /", p)]
            meta = " · ".join(parts)
            glance_cards.append(
                '<article class="card"><span class="icon">🌤️</span><h3>Времето днес</h3>'
                '<p class="glance-big">%s</p><p class="meta">%s</p>'
                '<a class="btn-ghost" href="vreme.html">Времето →</a></article>'
                % (esc(big), esc(meta))
            )
    now_hm = now.strftime("%H:%M")
    future = [e for e in upcoming
              if (e.get("date"), e.get("start") or "99:99") >= (today_iso, now_hm)]
    next_ev = future[0] if future else None
    if next_ev:
        ev_dt = datetime.strptime(next_ev["date"], "%Y-%m-%d")
        if next_ev["date"] == today_iso:
            when = "днес, %s" % (next_ev.get("start") or "")
        else:
            when = "%s, %s, %s" % (weekday_bg(ev_dt).capitalize(),
                                   ev_dt.strftime("%d.%m"),
                                   next_ev.get("start") or "")
        venue = (next_ev.get("venue") or "").strip()
        glance_cards.append(
            '<article class="card"><span class="icon">🎟️</span><h3>Следващо събитие</h3>'
            '<p class="glance-big">%s</p><p class="meta">%s%s</p>'
            '<a class="btn-ghost" href="events.html">Събития →</a></article>'
            % (esc(when), esc(next_ev["name"]),
               (" · " + esc(venue)) if venue else "")
        )
    glance_html = ""
    if glance_cards:
        glance_html = (
            '<section aria-labelledby="glance-h"><div class="container">'
            '<h2 id="glance-h">Днес накратко</h2>'
            '<div class="grid">%s</div></div></section>' % "".join(glance_cards)
        )

    # „Тази седмица" — брой събития по дни, с линк към деня в страницата Събития
    week_cells = []
    for i in range(7):
        d = now.date() + timedelta(days=i)
        iso = d.strftime("%Y-%m-%d")
        n = sum(1 for e in upcoming if e.get("date") == iso)
        cnt = "—" if n == 0 else ("1 събитие" if n == 1 else "%d събития" % n)
        cls = "week-day today" if i == 0 else "week-day"
        week_cells.append(
            '<a class="%s" href="events.html#day-%s">'
            '<span class="wd">%s</span><span class="wn">%d</span>'
            '<span class="wc">%s</span></a>'
            % (cls, iso, ["пон", "вт", "ср", "чт", "пт", "сб", "нд"][d.weekday()],
               d.day, cnt)
        )
    week_html = (
        '<section aria-labelledby="week-h"><div class="container">'
        '<h2 id="week-h">Тази седмица</h2>'
        '<div class="week-strip">%s</div></div></section>' % "".join(week_cells)
    )

    # решетка с разделите
    grid_cards = []
    grid_cards.append(
        '<article class="card"><span class="icon">📰</span><h3>Новини</h3>'
        '<p class="meta">%d новини от последните 10 дни</p>'
        '<a class="btn-ghost" href="news.html">Отвори →</a></article>' % len(articles)
    )
    grid_cards.append(
        '<article class="card"><span class="icon">🗓️</span><h3>Събития</h3>'
        '<p class="meta">%d събития от днес нататък · 🆓 %d безплатни</p>'
        '<a class="btn-ghost" href="events.html">Отвори →</a></article>'
        % (len(upcoming), free_count)
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
        + glance_html
        + week_html
        + '<section aria-labelledby="today-h"><div class="container">'
          '<div class="section-head"><h2 id="today-h">Днес</h2>'
          '<a href="news.html">Всички новини →</a></div>'
          '<div class="grid">%s%s</div>'
          '</div></section>'
        % (today_cards, events_card)
        + '<section aria-labelledby="sections-h"><div class="container">'
          '<h2 id="sections-h">Раздели</h2>'
          '<p class="section-intro">Всичко на едно място — избери раздел и чети на място.</p>'
          '<div class="grid">%s</div>'
          '</div></section>' % "".join(grid_cards)
    )
    sizes["index.html"] = write_page(
        "index.html", shell("index", "Новини, събития и справки", home_body))

    # ================= НОВИНИ (v3: статиите директно, без издания) =================
    if articles:
        latest_ed = news[-1]
        ref_date = latest_ed["date"]

        def day_date(day_str, ref):
            dd, mm = int(day_str[:2]), int(day_str[3:5])
            dt = datetime(ref.year, mm, dd)
            if dt > ref:
                dt = datetime(ref.year - 1, mm, dd)
            return dt

        days = {}
        for a in articles:
            days.setdefault(a["day"], []).append(a)
        day_sections = []
        for day in sorted(days, reverse=True):
            groups = {}
            for a in days[day]:
                groups.setdefault(a["ed"], []).append(a)
            group_html = []
            for ed in sorted(groups, key=lambda e: PART_ORDER.get(e, 9)):
                items_html = "".join(news_item_html(a) for a in groups[ed])
                group_html.append(
                    '<div class="news-ed-group" id="ed-%s-%s">'
                    '<h3 class="news-ed">%s %s</h3>%s</div>'
                    % (day.replace(".", "-"), ed, PART_EMOJI.get(ed, "📰"),
                       PART_LABEL.get(ed, ed), items_html)
                )
            dt = day_date(day, ref_date)
            day_sections.append(
                '<section class="news-day" id="day-%s"><div class="container">'
                '<h2>%s, %s <span class="count">· %d новини</span></h2>%s</div></section>'
                % (day.replace(".", "-"), weekday_bg(dt).capitalize(),
                   dt.strftime("%d.%m"), len(days[day]), "".join(group_html))
            )
        news_day_chips = ('<button type="button" class="fchip on" data-day="all">Всички дни</button>' +
                          "".join(
                              '<button type="button" class="fchip on" data-day="%s">%s %s</button>'
                              % (day, weekday_bg(day_date(day, ref_date)).capitalize()[:3], day)
                              for day in sorted(days, reverse=True)))
        news_body = (
            '<div class="container" id="top"><div class="page-hero">'
            '<p class="kicker">Новини</p><h1>Новини — сутрин, следобед и вечер</h1>'
            '<p class="lede">%d новини от последните 10 дни · чети направо тук, '
            'без да отваряш отделни файлове.</p></div></div>'
            '<div class="toolbar" id="newsFilters">'
            '<div class="tb-row" role="search">'
            '<button type="button" class="btn filter-toggle" id="newsFilterToggle" aria-expanded="false" aria-controls="newsPanel">'
            '<span aria-hidden="true">☰</span> Филтри <span class="tb-badge" hidden></span></button>'
            '<input id="q" type="search" placeholder="Търси в новините…" aria-label="Търси в новините">'
            '<button type="button" class="btn tb-clear" hidden>✕ <span class="tb-clear-txt">Изчисти</span></button>'
            '</div><div class="tb-panel" id="newsPanel">'
            '<span class="label">Категория:</span>'
            '<div class="chips" id="catChips">'
            '<button type="button" class="fchip on" data-cat="all">Всички</button>'
            '<button type="button" class="fchip" data-cat="ai">🤖 AI</button>'
            '<button type="button" class="fchip" data-cat="bg">🇧🇬 България</button>'
            '<button type="button" class="fchip" data-cat="world">🌍 Свят</button>'
            '</div>'
            '<span class="label">Ден:</span>'
            '<div class="chips" id="newsDayChips">%s</div>'
            '<button type="button" class="btn" id="newsToday">📅 Днес</button>'
            '</div></div>'
            '<div class="result-bar"><p class="count-line" id="count" aria-live="polite"></p>'
            '<p class="no-results" id="no-results" hidden>Няма съвпадения. Пробвай друга дума или „✕ Изчисти“ филтрите.</p></div>'
            '%s'
            % (len(articles), news_day_chips, "".join(day_sections))
        )
        sizes["news.html"] = write_page(
            "news.html", shell("news", "Новини", news_body))

    # ================= СЪБИТИЯ (v3: от регистъра, от днес нататък) =================
    if upcoming:
        last_crawl = max((e.get("first_seen") or "") for e in upcoming)
        new_count = sum(1 for e in upcoming if e.get("first_seen") == last_crawl)
        by_day = {}
        for e in upcoming:
            by_day.setdefault(e["date"], []).append(e)
        ev_sections = []
        for iso in sorted(by_day):
            dt = datetime.strptime(iso, "%Y-%m-%d")
            cards = "".join(event_card_html(e, new_date=last_crawl) for e in by_day[iso])
            ev_sections.append(
                '<section class="ev-day" id="day-%s"><div class="container">'
                '<h2>%s, %s <span class="count">· %d събития</span></h2>%s</div></section>'
                % (iso, weekday_bg(dt).capitalize(), dt.strftime("%d.%m"),
                   len(by_day[iso]), cards)
            )
        ev_day_chips = "".join(
            '<button type="button" class="fchip on" data-day="%s">%s %s</button>'
            % (iso, weekday_bg(datetime.strptime(iso, "%Y-%m-%d")).capitalize()[:3],
               datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m"))
            for iso in sorted(by_day)
        )
        ev_cats = sorted({e.get("category") or "" for e in upcoming if e.get("category")})
        ev_cat_chips = ('<button type="button" class="fchip on" data-cat="">Всички</button>' +
                        "".join('<button type="button" class="fchip" data-cat="%s">%s</button>'
                                % (esc(c), esc(c)) for c in ev_cats))
        ev_srcs = sorted({src_label(e.get("source")) for e in upcoming})
        ev_src_chips = ('<button type="button" class="fchip on" data-src="">Всички</button>' +
                        "".join('<button type="button" class="fchip" data-src="%s">%s</button>'
                                % (esc(s), esc(s)) for s in ev_srcs))
        events_body = (
            '<div class="container" id="top"><div class="page-hero">'
            '<p class="kicker">Събития</p><h1>Събития — от днес нататък</h1>'
            '<p class="lede">%d събития · 🆓 %d безплатни · 🆕 %d нови · всички събрани събития, '
            'подредени по дни. Старите не се показват.</p></div></div>'
            '<div class="toolbar" id="evFilters">'
            '<div class="tb-row" role="search">'
            '<button type="button" class="btn filter-toggle" id="evFilterToggle" aria-expanded="false" aria-controls="evPanel">'
            '<span aria-hidden="true">☰</span> Филтри <span class="tb-badge" hidden></span></button>'
            '<input id="q" type="search" placeholder="Търси в събитията…" aria-label="Търси в събитията">'
            '<button type="button" class="btn tb-clear" hidden>✕ <span class="tb-clear-txt">Изчисти</span></button>'
            '</div><div class="tb-panel" id="evPanel">'
            '<span class="label">Дни:</span>'
            '<div class="chips" id="evDayChips">%s</div>'
            '<button type="button" class="btn" id="evAllDays">Всички дни</button>'
            '<button type="button" class="btn" id="evWeekend">🎉 Този уикенд</button>'
            '<button type="button" class="btn" id="evToday">📅 Днес</button>'
            '<span class="label">Категории:</span>'
            '<div class="chips" id="evCatChips">%s</div>'
            '<span class="label">Източник:</span>'
            '<div class="chips" id="evSrcChips">%s</div>'
            '<span class="label">Разстояние:</span>'
            '<div class="chips" id="evDistChips">'
            '<button type="button" class="fchip on" data-dist="">Всички</button>'
            '<button type="button" class="fchip" data-dist="sofia">София</button>'
            '<button type="button" class="fchip" data-dist="far">🚗 По-далече</button></div>'
            '<span class="label">Още:</span>'
            '<div class="chips">'
            '<button type="button" class="fchip" id="evFreeBtn">🆓 само безплатни</button>'
            '<button type="button" class="fchip" id="evNewBtn">🆕 само нови</button>'
            '<button type="button" class="fchip" id="evTimeBtn">⏰ само с посочен час</button></div>'
            '</div></div>'
            '<div class="result-bar"><p class="count-line" id="count" aria-live="polite"></p>'
            '<p class="no-results" id="no-results" hidden>Няма съвпадения. Пробвай друга дума или „✕ Изчисти“ филтрите.</p></div>'
            '%s'
            % (len(upcoming), free_count, new_count, ev_day_chips, ev_cat_chips,
               ev_src_chips, "".join(ev_sections))
        )
        sizes["events.html"] = write_page(
            "events.html", shell("events", "Събития", events_body))
    else:
        events_body = (
            '<div class="container" id="top"><div class="page-hero">'
            '<p class="kicker">Събития</p><h1>Събития — от днес нататък</h1>'
            '<p class="lede">Няма предстоящи събития в регистъра — '
            'страницата се обновява при следващ sync.</p></div></div>'
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
    for a in articles:
        search_entries.append({
            "t": a["title"],
            "d": "%s · %s" % (a["day"], PART_LABEL.get(a["ed"], a["ed"])),
            "k": "Новини",
            "u": "news.html#day-%s" % a["day"].replace(".", "-"),
            "s": a["text"][:300],
        })
    for e in upcoming:
        dt = datetime.strptime(e["date"], "%Y-%m-%d")
        search_entries.append({
            "t": e.get("name", ""),
            "d": "%s, %s %s · %s" % (fmt_date(dt), weekday_bg(dt),
                                     (e.get("start") or ""), e.get("venue", "")),
            "k": "Събития",
            "u": "events.html#ev-%s" % e.get("number", ""),
            "s": "%s %s" % (e.get("category", ""),
                            truncate_text(e.get("description_bg", ""), 200)),
        })
    for sec_id, nav_label, title, intro, fname, emoji in single_defs:
        if fname not in singles:
            continue
        search_entries.append({
            "t": title, "d": "", "k": "Страница",
            "u": "%s.html" % sec_id,
            "s": plain_text(read_file(fname), 300),
        })
    with open(os.path.join(SITE_DIR, "search.json"), "w", encoding="utf-8") as f:
        json.dump(search_entries, f, ensure_ascii=False)
    search_body = (
        '<div class="container" id="top"><div class="page-hero">'
        '<p class="kicker">Търсене</p><h1>Търси в новините и събитията</h1>'
        '<p class="lede">В новините и събитията — наведнъж.</p></div>'
        '<div class="searchbar" role="search">'
        '<input id="q" type="search" placeholder="Напиши дума — например преход, джаз, концерт…" aria-label="Търси в новините и събитията">'
        '<p class="count-line" id="count" aria-live="polite"></p>'
        '</div><div id="results"><p class="no-results">Напиши дума — търси в новините и събитията.</p></div>'
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
        "total": len(news) + len(upcoming) + len(singles),
        "news": len(articles), "digest": len(digests),
        "radar": 1 if "radar-actions.html" in singles else 0,
        "cars": 1 if "cars-dashboard.html" in singles else 0,
        "aiplan": 1 if "udemy-plan-2026-11-05-site.html" in singles else 0,
        "events": len(upcoming),
        "weather": 1 if "weather.html" in singles else 0,
        "scout": len(scout_files),
        "other": len(other_events),
    }
    print("INDEX: total=%d news=%d events=%d radar=%d cars=%d aiplan=%d "
          "weather=%d scout=%d other=%d updated=%s"
          % (counts["total"], counts["news"], counts["events"],
             counts["radar"], counts["cars"], counts["aiplan"],
             counts["weather"], counts["scout"],
             counts["other"], updated))
    print("INDEX-SIZE: " + " ".join("%s=%d" % (k, v) for k, v in sorted(sizes.items())))


if __name__ == "__main__":
    main()
