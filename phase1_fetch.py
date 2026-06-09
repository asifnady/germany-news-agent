"""
Phase 1: Fetch all RSS feeds and print raw German output.
Tests that all feed URLs work from this Python environment.
"""
import urllib.request
import xml.etree.ElementTree as ET
import ssl
from datetime import datetime

FEEDS = {
    "SZ Furstenfeldbruck": "https://rss.sueddeutsche.de/fuerstenfeldbruck",
    "SZ Munchen": "https://rss.sueddeutsche.de/rss/Muenchen",
    "SZ Bayern": "https://rss.sueddeutsche.de/rss/Bayern",
    "Bild Munchen": "http://www.bild.de/rss-feeds/rss-16725492,feed=muenchen.bild.html",
    "FAZ": "https://www.faz.net/rss/aktuell",
    "Spiegel Panorama": "https://www.spiegel.de/panorama/index.rss",
    "Merkur FFB": "https://www.merkur.de/lokales/fuerstenfeldbruck/rssfeed.rdf",
    "Presseportal Blaulicht": "https://www.presseportal.de/blaulicht/rss",
}

ctx = ssl.create_default_context()

def fetch_rss(name, url):
    print(f"\n{'='*60}")
    print(f"[FEED] {name}")
    print(f"   URL: {url}")
    print(f"{'='*60}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            raw = resp.read()
        print(f"   [OK] Status: {resp.status}")
        print(f"   [BYTES] Size: {len(raw)} bytes")
        
        # Parse RSS
        root = ET.fromstring(raw)
        items = []
        # Handle both RSS 2.0 and RDF formats
        channel = root.find("channel")
        if channel is not None:
            items = channel.findall("item")
        else:
            # RDF format
            items = root.findall(".//{http://purl.org/rss/1.0/}item") or root.findall(".//item")
        
        count = len(items)
        print(f"   [ITEMS] Articles: {count}")
        
        # Show top 3 articles
        for i, item in enumerate(items[:3]):
            ns = {"dc": "http://purl.org/dc/elements/1.1/"}
            title = item.findtext("title", "N/A")
            desc = item.findtext("description", "")
            if desc:
                desc = desc[:150].replace("\n", " ").strip()
            pub = item.findtext("pubDate", "")[:16] if item.findtext("pubDate") else ""
            creator = item.findtext("dc:creator", "", ns)
            print(f"\n   [{i+1}] {title}")
            if creator:
                print(f"       By: {creator}")
            if pub:
                print(f"       When: {pub}")
            if desc:
                print(f"       {desc}...")
        
        if count > 3:
            print(f"\n   ... and {count - 3} more articles")
            
    except Exception as e:
        print(f"   [ERR] {type(e).__name__}: {e}")

if __name__ == "__main__":
    print(f"=== Test run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"--- Testing {len(FEEDS)} RSS feeds...")
    
    for name, url in FEEDS.items():
        fetch_rss(name, url)
    
    print(f"\n{'='*60}")
    print("Phase 1 complete!")
