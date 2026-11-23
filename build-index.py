#!/usr/bin/env python3
# build-index.py — генерира index.html за сайта с дайджестите.
# Чете *.html в същата папка, групира ги по вид, сортира по дата (низходящо)
# и пише index.html. Детерминистичен: същият вход дава същия изход —
# "последно обновление" е mtime на най-новия файл, не текущото време,
# за да не се променя index.html при всяко пускане без нови файлове.
# Лог: по един ред на група + общ брой.
import os
import re
from datetime import datetime

SITE = os.path.dirname(os.path.abspath(__file__))
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)

GROUPS = [
    ("news", "Новини"),
    ("digest", "Събития — дневен дайджест"),
    ("podari", "Подари Време"),
    ("radar", "RADAR действия"),
    ("cars", "Коли"),
    ("aiplan", "AI план за учене"),
    ("events", "Събития — други"),
    ("other", "Други"),
]


def doc_title(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            head = f.read(4096)
        m = TITLE_RE.search(head)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    except OSError:
        pass
    return None


def parse_date(name):
    m = DATE_RE.search(name)
    return m.group(0) if m else None


def fmt_date(iso):
    y, m, d = iso.split("-")
    return "%s.%s.%s" % (d, m, y)


def collect():
    files = []
    for name in sorted(os.listdir(SITE)):
        if not name.endswith(".html"):
            continue
        if name == "index.html":
            continue
        if name.endswith("-share.html") or "test" in name.lower():
            continue
        path = os.path.join(SITE, name)
        if not os.path.isfile(path):
            continue
        if os.path.getsize(path) < 1024:
            continue
        files.append((name, path))
    return files


def classify(name):
    if name.startswith("novini-"):
        return "news"
    if name.startswith("digest-"):
        return "digest"
    if name == "podari-vreme.html":
        return "podari"
    if name == "radar-actions.html":
        return "radar"
    if name == "cars-dashboard.html":
        return "cars"
    if name.startswith("udemy-plan"):
        return "aiplan"
    if name.startswith("events-"):
        return "events"
    return "other"


def sort_key(item):
    name, path = item
    d = parse_date(name) or "0000-00-00"
    return (d, os.path.getmtime(path))


def part_label(name):
    if "morning" in name:
        return "сутрин"
    if "afternoon" in name:
        return "следобед"
    if "evening" in name:
        return "вечер"
    return ""


def main():
    files = collect()
    grouped = {key: [] for key, _ in GROUPS}
    for item in files:
        grouped[classify(item[0])].append(item)
    for items in grouped.values():
        items.sort(key=sort_key, reverse=True)

    latest = max((os.path.getmtime(p) for _, p in files), default=None)
    updated = datetime.fromtimestamp(latest).strftime("%d.%m.%Y %H:%M") if latest else "—"

    out = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="bg"><head><meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append("<title>Моите дайджести</title>")
    out.append("<style>")
    out.append("body{margin:0;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;color:#212121}")
    out.append("header{background:#1565c0;color:#fff;padding:20px 16px}")
    out.append("header h1{margin:0 0 4px;font-size:24px}header p{margin:2px 0;font-size:14px;opacity:.92}")
    out.append("main{max-width:720px;margin:0 auto;padding:12px}")
    out.append("section{background:#fff;border-radius:12px;padding:14px 16px;margin:0 0 12px;box-shadow:0 1px 4px rgba(0,0,0,.1)}")
    out.append("h2{margin:0 0 10px;font-size:18px}")
    out.append(".row{padding:8px 0;border-bottom:1px solid #eee;font-size:15px;line-height:1.5}")
    out.append(".row:last-child{border-bottom:none}")
    out.append("a{color:#1565c0;text-decoration:none}a:hover{text-decoration:underline}")
    out.append(".date{font-weight:700}.sep{color:#999;margin:0 6px}")
    out.append("</style></head><body>")
    out.append("<header><h1>Моите дайджести</h1>")
    out.append("<p>Новини, събития и справки — обновява се автоматично.</p>")
    out.append("<p>Последно обновление: %s</p></header>" % updated)
    out.append("<main>")

    # Новини — по дни, с трите издания на реда
    news = grouped["news"]
    if news:
        days = {}
        for name, _ in news:
            d = parse_date(name) or "без дата"
            days.setdefault(d, []).append(name)
        out.append("<section><h2>Новини</h2>")
        for d in sorted(days, reverse=True):
            label = fmt_date(d) if d != "без дата" else d
            links = []
            for name in sorted(days[d]):
                part = part_label(name)
                links.append('<a href="%s">%s</a>' % (name, part or "обзор"))
            out.append('<div class="row"><span class="date">%s</span><span class="sep">—</span>%s</div>'
                       % (label, " <span class='sep'>|</span> ".join(links)))
        out.append("</section>")

    # Дайджест — по дати
    digest = grouped["digest"]
    if digest:
        out.append("<section><h2>Събития — дневен дайджест</h2>")
        for name, _ in digest:
            d = parse_date(name)
            label = fmt_date(d) if d else name
            out.append('<div class="row"><a href="%s">%s</a></div>' % (name, label))
        out.append("</section>")

    # Единични документи
    singles = [("podari", "Подари Време"), ("radar", "RADAR действия"),
               ("cars", "Коли"), ("aiplan", "AI план за учене")]
    for key, title in singles:
        items = grouped[key]
        if not items:
            continue
        out.append("<section><h2>%s</h2>" % title)
        for name, path in items:
            t = doc_title(path) or name
            out.append('<div class="row"><a href="%s">%s</a></div>' % (name, t))
        out.append("</section>")

    # Други
    rest = grouped["events"] + grouped["other"]
    if rest:
        rest.sort(key=sort_key, reverse=True)
        out.append("<section><h2>Други</h2>")
        for name, path in rest:
            t = doc_title(path) or name
            out.append('<div class="row"><a href="%s">%s</a></div>' % (name, t))
        out.append("</section>")

    out.append("</main></body></html>")
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    counts = {key: len(grouped[key]) for key, _ in GROUPS}
    total = sum(counts.values())
    print("INDEX: total=%d news=%d digest=%d podari=%d radar=%d cars=%d aiplan=%d events=%d other=%d updated=%s"
          % (total, counts["news"], counts["digest"], counts["podari"], counts["radar"],
             counts["cars"], counts["aiplan"], counts["events"], counts["other"], updated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
