"""
Phase 2: Keyword filtering, location prioritization, and regional grouping.
Top 5 local, top 5 Bavaria, top 5 Germany.
"""
import urllib.request
import xml.etree.ElementTree as ET
import ssl
import re
from datetime import datetime

FEEDS = {
    "SZ FFB (local)": "https://rss.sueddeutsche.de/fuerstenfeldbruck",
    "SZ Munchen": "https://rss.sueddeutsche.de/rss/Muenchen",
    "SZ Bayern": "https://rss.sueddeutsche.de/rss/Bayern",
    "Bild Munchen": "http://www.bild.de/rss-feeds/rss-16725492,feed=muenchen.bild.html",
    "FAZ": "https://www.faz.net/rss/aktuell",
    "Spiegel Deutschland": "https://www.spiegel.de/politik/deutschland/index.rss",
    "Merkur FFB (local)": "https://www.merkur.de/lokales/fuerstenfeldbruck/rssfeed.rdf",
    "Presseportal Blaulicht": "https://www.presseportal.de/blaulicht/rss",
}

# --- KEYWORD TIERS ---
TIER1_KEYWORDS = [
    "fuerstenfeldbruck", "furstenfeldbruck", "ffb", "germering",
    "puchheim", "olching", "groebenzell", "grobenzell", "maisach",
    "freiheim", "pasing", "neuaubing", "bruck",
    "moorenweis", "landsberied", "adelshofen", "alling",
    "mittelstetten", "emmering", "eichenau", "kottgeisering",
    "schoengeising", "turkenfeld", "jesenwang", "mammendorf",
    "hattenhofen",
]

TIER2_KEYWORDS = [
    "muenchen", "munchen", "munich",
    "dachau", "starnberg", "freising", "erding", "ebersberg",
    "wolfratshausen", "garmisch", "weilheim",
    "schongau", "holzkirchen", "miesbach",
]

TIER3_KEYWORDS = [
    "bayern", "bavaria", "bayerisch",
]

ALL_TIER1 = "|".join(TIER1_KEYWORDS)
ALL_TIER2 = "|".join(TIER2_KEYWORDS)
ALL_TIER3 = "|".join(TIER3_KEYWORDS)

ctx = ssl.create_default_context()


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_tier(title, desc, creator, feed_name):
    # Check title + description + creator for keywords
    text = (title + " " + (desc or "") + " " + (creator or "")).lower()
    
    # First check explicit keyword matches
    if re.search(ALL_TIER1, text):
        return 1
    if re.search(ALL_TIER2, text):
        return 2
    if re.search(ALL_TIER3, text):
        return 3
    
    # Feed-based boost: articles from explicitly local feeds default to Tier 2
    feed_lower = feed_name.lower()
    if "ffb" in feed_lower or "local" in feed_lower or "merkur" in feed_lower:
        return 2
    
    return 4


def parse_feed(name, url):
    articles = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            raw = resp.read()

        root = ET.fromstring(raw)
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else (
            root.findall(".//{http://purl.org/rss/1.0/}item") or root.findall(".//item")
        )

        for item in items:
            ns = {"dc": "http://purl.org/dc/elements/1.1/"}
            title = item.findtext("title", "")
            desc_raw = item.findtext("description", "")
            desc = strip_html(desc_raw)
            link = item.findtext("link", "")
            pub = item.findtext("pubDate", "")
            creator = item.findtext("dc:creator", "", ns)

            articles.append({
                "source": name,
                "title": title,
                "desc": desc,
                "link": link,
                "pub_date": pub,
                "creator": creator,
                "tier": get_tier(title, desc, creator, name),
            })

    except Exception as e:
        print(f"  [ERR] {name}: {type(e).__name__}: {e}")

    return articles


def print_article(i, article):
    desc = article["desc"][:120].strip() if article["desc"] else ""
    print(f"\n  [{i}] {article['title']}")
    print(f"      {article['source'].split(' (')[0]}")
    if desc:
        print(f"      {desc}...")
    print(f"      {article['link']}")


if __name__ == "__main__":
    print(f"=== Phase 2: Filtering + Ranking ===")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_articles = []

    for name, url in FEEDS.items():
        print(f"Fetching: {name}...")
        items = parse_feed(name, url)
        print(f"  -> {len(items)} articles")
        all_articles.extend(items)

    print(f"\n{'='*60}")
    print(f"Total articles: {len(all_articles)}")

    # Sort by tier
    all_articles.sort(key=lambda a: a["tier"])

    # Counts
    for t in range(1, 5):
        cnt = sum(1 for a in all_articles if a["tier"] == t)
        label = {1: "FFB/Germering", 2: "Munich area", 3: "Bavaria", 4: "General"}[t]
        print(f"  Tier {t} ({label}): {cnt}")

    # Group into sections
    tier_groups = {1: [], 2: [], 3: [], 4: []}
    for a in all_articles:
        tier_groups[a["tier"]].append(a)

    sections = [
        ("LOCAL (Munich / FFB / Germering)", tier_groups[1] + tier_groups[2], 5),
        ("BAVARIA", tier_groups[3], 5),
        ("GERMANY", tier_groups[4], 5),
    ]

    print(f"\n{'='*60}")
    print("TOP STORIES BY REGION")
    print(f"{'='*60}")

    for section_name, articles, limit in sections:
        top = articles[:limit]
        print(f"\n{'-'*60}")
        print(f"[ {section_name} ] ({len(top)} stories)")
        print(f"{'-'*60}")

        if not top:
            print("  (No articles in this region)")
            continue

        for i, article in enumerate(top, 1):
            print_article(i, article)

    print(f"\n{'='*60}")
    print("Phase 2 complete!")
