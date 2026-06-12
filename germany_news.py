"""
Germany News Agent: Fetch, filter, translate, and format top news.
Reads config.json for all settings — edit that file, not this one.
"""
import json, os, re, ssl, sys, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import argostranslate.package, argostranslate.translate

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Load config ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, encoding="utf-8") as f:
    CFG = json.load(f)

FEEDS = CFG["feeds"]
FEED_BOOST = CFG.get("feed_boost", [])

TIER1 = CFG["keywords"]["tier1"]
TIER2 = CFG["keywords"]["tier2"]
TIER3 = CFG["keywords"]["tier3"]
RE_T1 = re.compile("|".join(TIER1), re.IGNORECASE)
RE_T2 = re.compile("|".join(TIER2), re.IGNORECASE)
RE_T3 = re.compile("|".join(TIER3), re.IGNORECASE)

COMPACT = CFG["compact_counts"]
DETAILED_LIMIT = CFG.get("detailed_per_source", 5)

ctx = ssl.create_default_context()

# --- Translation ---
_translator_ready = False
def setup_translator():
    global _translator_ready
    if _translator_ready:
        return
    # Check if de→en translation works (model already on disk)
    try:
        test = argostranslate.translate.translate("Hallo", "de", "en")
        _translator_ready = True
        return
    except Exception:
        pass
    # Need to download and install
    argostranslate.package.update_package_index()
    for pkg in argostranslate.package.get_available_packages():
        if pkg.from_code == "de" and pkg.to_code == "en":
            download_path = pkg.download()
            argostranslate.package.install_from_path(download_path)
            _translator_ready = True
            return

def translate(text):
    if not text or not text.strip():
        return ""
    try:
        return argostranslate.translate.translate(text, "de", "en")
    except Exception as e:
        print(f"  [translate error] {e}", file=sys.stderr)
        return text

# --- Feed helpers ---
def strip_html(t):
    if not t: return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()

def get_tier(title, desc, creator, feed_name):
    text = f"{title} {desc or ''} {creator or ''}".lower()
    if RE_T1.search(text): return 1
    if RE_T2.search(text): return 2
    if RE_T3.search(text): return 3
    if feed_name in FEED_BOOST: return 2
    return 4

def fetch_feed(name, url, max_items=None):
    articles = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            root = ET.fromstring(resp.read())
        channel = root.find("channel")
        items = (channel.findall("item") if channel is not None else
                 root.findall(".//{http://purl.org/rss/1.0/}item") or root.findall(".//item"))
        ns = {"dc": "http://purl.org/dc/elements/1.1/"}
        # RSS feeds are newest-first, so first N items = latest N
        if max_items:
            items = items[:max_items]
        for item in items:
            articles.append({
                "source": name,
                "title": item.findtext("title", ""),
                "desc": strip_html(item.findtext("description", "")),
                "link": item.findtext("link", ""),
                "pub_date": item.findtext("pubDate", ""),
                "creator": item.findtext("dc:creator", "", ns),
                "tier": get_tier(item.findtext("title", ""),
                                 strip_html(item.findtext("description", "")),
                                 item.findtext("dc:creator", "", ns), name),
            })
    except Exception:
        pass
    return articles

# --- Output formatting ---
def fmt_article(a, with_desc=True):
    en_title = translate(a["title"])
    en_desc = translate(a["desc"]) if a["desc"] and with_desc else ""
    lines = [f"**{en_title}**", f"`{a['source']}`"]
    if en_desc:
        d = en_desc[:250].strip()
        if len(en_desc) > 250: d += "..."
        lines.append(d)
    lines.append(f"<{a['link']}>")
    return "\n".join(lines)

def fmt_article_numbered(a, num, with_desc=True):
    """Format an article with a flat number prefix."""
    en_title = translate(a["title"])
    en_desc = translate(a["desc"]) if a["desc"] and with_desc else ""
    lines = [f"**{num}.** {en_title}", f"`{a['source']}`"]
    if en_desc:
        d = en_desc[:250].strip()
        if len(en_desc) > 250: d += "..."
        lines.append(d)
    lines.append(f"<{a['link']}>")
    return "\n".join(lines)

def pick_mixed(articles, count):
    if not articles: return []
    sources = {}
    for a in articles:
        sources.setdefault(a["source"], []).append(a)
    result, taken = [], set()
    keys, idxs = list(sources.keys()), {s: 0 for s in sources}
    while len(result) < count and len(taken) < len(articles):
        for src in keys:
            if len(result) >= count: break
            i = idxs[src]
            while i < len(sources[src]):
                if sources[src][i]["link"] not in taken:
                    result.append(sources[src][i])
                    taken.add(sources[src][i]["link"])
                    idxs[src] = i + 1
                    break
                i += 1
    return result

def now_str():
    return datetime.now(timezone(timedelta(hours=2))).strftime("%d %B %Y")

# --- Article mapping for @Tipu <number> replies ---
MAPPING_PATH = os.path.join(SCRIPT_DIR, "last_news_articles.json")

def save_article_mapping(article_map, mode):
    """Save flat article mapping for @Tipu <number> lookups."""
    payload = {
        "timestamp": datetime.now(timezone(timedelta(hours=2))).isoformat(),
        "mode": mode,
        "articles": article_map
    }
    with open(MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"  [mapping] Saved {len(article_map)} articles to {MAPPING_PATH}", file=sys.stderr)

# --- Modes ---
def run_compact():
    setup_translator()
    all_a = []
    for n, u in FEEDS.items():
        items = fetch_feed(n, u)
        all_a.extend(items)
        print(f"  [{n}] {len(items)} articles", file=sys.stderr)
    all_a.sort(key=lambda a: a["tier"])
    groups = {1: [], 2: [], 3: [], 4: []}
    for a in all_a: groups[a["tier"]].append(a)
    sections = [
        ("LOCAL", groups[1] + groups[2], COMPACT["local"]),
        ("BAVARIA", groups[3], COMPACT["bavaria"]),
        ("GERMANY", groups[4], COMPACT["germany"]),
    ]
    msg = f"**Germany News Weekly** — {now_str()}\n\n"
    article_map = {}
    flat_num = 0
    for sn, arts, lim in sections:
        top = pick_mixed(arts, lim)
        msg += f"__**{sn}**__\n"
        if not top:
            msg += "_No stories this week._\n\n"
            continue
        for a in top:
            flat_num += 1
            article_map[str(flat_num)] = {
                "source": a["source"],
                "title": a["title"],
                "url": a["link"],
                "rss_desc": a["desc"]
            }
            msg += f"\n{fmt_article_numbered(a, flat_num)}\n"
        msg += "\n"
    msg += "_Reply with `@Tipu <number>` for a detailed summary of an article._"
    save_article_mapping(article_map, "compact")
    return msg

DETAILED_FETCH_PER_FEED = 15  # fetch 15 per feed so each source can fill 5 articles per tier

def run_detailed():
    setup_translator()
    all_a = []
    for n, u in FEEDS.items():
        items = fetch_feed(n, u, max_items=DETAILED_FETCH_PER_FEED)
        all_a.extend(items)
        print(f"  [{n}] {len(items)} articles", file=sys.stderr)
    all_a.sort(key=lambda a: a["tier"])
    article_map = {}
    flat_num = 0
    tiers = {1: [], 2: [], 3: [], 4: []}
    for a in all_a: tiers[a["tier"]].append(a)
    combined = [
        ("LOCAL (FFB Region)", tiers[1] + tiers[2]),
        ("BAVARIA", tiers[3]),
        ("GERMANY", tiers[4]),
    ]
    msg = f"**Germany News — Full Details** — {now_str()}\n\n"
    for sn, arts in combined:
        if not arts:
            continue
        msg += f"__**{sn}**__\n\n"
        by_src = {}
        for a in arts: by_src.setdefault(a["source"], []).append(a)
        for src in sorted(by_src.keys()):
            top = by_src[src][:DETAILED_LIMIT]
            msg += f"**{src}** ({len(top)} articles)\n"
            for a in top:
                flat_num += 1
                article_map[str(flat_num)] = {
                    "source": a["source"],
                    "title": a["title"],
                    "url": a["link"],
                    "rss_desc": a["desc"]
                }
                en_title = translate(a["title"])
                msg += f"{flat_num}. **{en_title}**\n"
                en_desc = translate(a["desc"]) if a["desc"] else ""
                if en_desc:
                    msg += f"   {en_desc[:200].strip()}\n"
                msg += f"   <{a['link']}>\n"
            msg += "\n"
        msg += "\n"
    msg += f"_Top {DETAILED_LIMIT} per source shown. Reply with `@Tipu <number>` for a detailed summary._"
    save_article_mapping(article_map, "detailed")
    return msg

if __name__ == "__main__":
    detailed = "--detailed" in sys.argv[1:]
    if detailed:
        result = run_detailed()
    else:
        print("Fetching and translating news...", file=sys.stderr)
        result = run_compact()
    print(result)
