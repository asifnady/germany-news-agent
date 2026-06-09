"""
Germany News Agent: Fetch, filter, translate, and format top news.
Reads config.json for all settings — edit that file, not this one.
"""
import json, os, re, ssl, sys, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import argostranslate.package, argostranslate.translate

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
def setup_translator():
    installed = argostranslate.translate.get_installed_languages()
    for lang in installed:
        if lang.code == "de":
            for trans in lang.translations_to:
                if hasattr(trans, 'to_lang') and trans.to_lang.code == "en":
                    return
    argostranslate.package.update_package_index()
    for pkg in argostranslate.package.get_available_packages():
        if pkg.from_code == "de" and pkg.to_code == "en":
            download_path = pkg.download()
            argostranslate.package.install_from_path(download_path)
            return

def translate(text):
    if not text or not text.strip():
        return ""
    try:
        return argostranslate.translate.translate(text, "de", "en")
    except:
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

def fetch_feed(name, url):
    articles = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            root = ET.fromstring(resp.read())
        channel = root.find("channel")
        items = (channel.findall("item") if channel is not None else
                 root.findall(".//{http://purl.org/rss/1.0/}item") or root.findall(".//item"))
        ns = {"dc": "http://purl.org/dc/elements/1.1/"}
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
    for sn, arts, lim in sections:
        top = pick_mixed(arts, lim)
        msg += f"__**{sn}**__\n"
        if not top:
            msg += "_No stories this week._\n\n"
            continue
        for i, a in enumerate(top, 1):
            msg += f"\n**{i}.** {fmt_article(a)}\n"
        msg += "\n"
    msg += "_Summary runs every Monday 09:30 CET. Use `--detailed` flag for per-source breakdown._"
    return msg

def run_detailed():
    setup_translator()
    all_a = []
    for n, u in FEEDS.items():
        items = fetch_feed(n, u)
        all_a.extend(items)
        print(f"  [{n}] {len(items)} articles", file=sys.stderr)
    all_a.sort(key=lambda a: a["tier"])
    tiers = {1: [], 2: [], 3: [], 4: []}
    for a in all_a: tiers[a["tier"]].append(a)
    combined = [
        ("LOCAL", tiers[1] + tiers[2]),
        ("BAVARIA", tiers[3]),
        ("GERMANY", tiers[4]),
    ]
    msg = f"**Germany News — Full Details** — {now_str()}\n\n"
    for sn, arts in combined:
        msg += f"__**{sn}**__\n\n"
        by_src = {}
        for a in arts: by_src.setdefault(a["source"], []).append(a)
        for src in sorted(by_src.keys()):
            top = by_src[src][:DETAILED_LIMIT]
            msg += f"**{src}** ({len(top)} articles)\n"
            for i, a in enumerate(top, 1):
                en_title = translate(a["title"])
                msg += f"{i}. **{en_title}**\n"
                en_desc = translate(a["desc"]) if a["desc"] else ""
                if en_desc:
                    msg += f"   {en_desc[:200].strip()}\n"
                msg += f"   <{a['link']}>\n"
            msg += "\n"
        msg += "\n"
    msg += "_Full detailed summary._"
    return msg

if __name__ == "__main__":
    detailed = "--detailed" in sys.argv[1:]
    if detailed:
        result = run_detailed()
    else:
        print("Fetching and translating news...", file=sys.stderr)
        result = run_compact()
    print(result)
