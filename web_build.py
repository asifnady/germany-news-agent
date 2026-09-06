r"""
Germany News Agent — daily offline web build.

Fetches all configured feeds, filters by tier (same logic as germany_news.py),
translates headlines + lead summaries German→English (online fallback chain with
a persistent cache so repeated stories cost nothing), then writes:

  web/data/news/YYYY-MM-DD.json   — one file per day
  web/data/latest.json            — copy of the newest day
  web/data/days.json              — date index (newest first)
  web/data/cache.json             — persistent DE→EN translation cache
  last_news_articles.json         — so @Tipu <number> replies use the newest set

Consumed by web/server.js (zero-dep Node server for the internal WLAN page).

Run from repo root:
  .venv\Scripts\python.exe web_build.py

Safe to run repeatedly: identical dates overwrite, old days (30+) are pruned,
and a totally failed fetch (zero articles) leaves the previous data untouched.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import germany_news as gn   # fetch_feed / pick_mixed / save_article_mapping
import summarize            # translate() chain: gtx → dict-chrome-ex → MyMemory

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "web" / "data"
NEWS_DIR = DATA_DIR / "news"
CACHE_PATH = DATA_DIR / "cache.json"
MAX_DAYS_KEPT = 30

# Section name → (tier set, article cap). Tune caps freely.
SECTIONS = [
    ("LOCAL (FFB Region)", {1, 2}, 12),
    ("BAVARIA", {3}, 7),
    ("GERMANY", {4}, 7),
]
FETCH_PER_FEED = 15

for d in (DATA_DIR, NEWS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- Persistent DE→EN translation cache -----------------------------------
_cache = {}
_cache_dirty = 0


def load_cache():
    global _cache
    try:
        _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _cache = {}


def save_cache():
    CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")


def tr(text):
    """Translate short DE text → EN, memoized to web/data/cache.json."""
    global _cache_dirty
    text = (text or "").strip()
    if not text:
        return ""
    hit = _cache.get(text)
    if hit:
        return hit
    out = summarize.translate(text)  # returns original text if all endpoints fail
    if out and out != text:
        if len(text) <= 400:
            _cache[text] = out
            _cache_dirty += 1
            if _cache_dirty >= 25:
                save_cache()
                _cache_dirty = 0
        return out
    return out or text


def build():
    load_cache()
    all_a = []
    for name, url in gn.FEEDS.items():
        items = gn.fetch_feed(name, url, max_items=FETCH_PER_FEED)
        all_a.extend(items)
        print(f"  [{name}] {len(items)} articles", file=sys.stderr)
    if not all_a:
        raise SystemExit("ERROR: no articles fetched — previous day's data left untouched.")

    now = datetime.now().astimezone()  # host is Europe/Berlin; DST-safe
    date = now.strftime("%Y-%m-%d")
    sections_out, article_map, flat = [], {}, 0
    for sec_name, tiers, cap in SECTIONS:
        arts = [a for a in all_a if a["tier"] in tiers]
        top = gn.pick_mixed(arts, cap)
        out = []
        for a in top:
            flat += 1
            en_title = tr(a["title"])
            en_sum = tr(a["desc"]) if a.get("desc") else ""
            desc_de = a.get("desc") or ""
            out.append({
                "id": flat,
                "source": a["source"],
                "title": en_title,
                "title_de": a["title"],
                "summary": (en_sum[:600].rstrip() + ("…" if len(en_sum) > 600 else "")) or None,
                "summary_de": (desc_de[:600].rstrip() + ("…" if len(desc_de) > 600 else "")) if desc_de else "",
                "url": a["link"],
                "published": a.get("pub_date") or "",
            })
            article_map[str(flat)] = {
                "source": a["source"],
                "title": a["title"],
                "url": a["link"],
                "rss_desc": desc_de,
            }
        if out:
            sections_out.append({"name": sec_name, "articles": out})

    payload = {
        "date": date,
        "generatedAt": now.isoformat(timespec="seconds"),
        "total": flat,
        "sections": sections_out,
    }
    (NEWS_DIR / f"{date}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA_DIR / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    days = sorted({p.stem for p in NEWS_DIR.glob("*.json")}, reverse=True)
    (DATA_DIR / "days.json").write_text(json.dumps(days), encoding="utf-8")

    cutoff = (datetime.now().astimezone() - timedelta(days=MAX_DAYS_KEPT)).strftime("%Y-%m-%d")
    for p in NEWS_DIR.glob("*.json"):
        if p.stem < cutoff:
            p.unlink(missing_ok=True)

    gn.save_article_mapping(article_map, "web")
    save_cache()
    print(f"  OK {date}: {flat} articles, {len(sections_out)} sections → web/data/news/{date}.json",
          file=sys.stderr)


if __name__ == "__main__":
    build()
