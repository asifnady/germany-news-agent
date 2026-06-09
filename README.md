# Germany News Agent 🐅

A Python tool that fetches German news from RSS feeds, translates them to English (offline, free), and delivers a curated summary — no API costs.

## How it works

1. **Fetches** RSS feeds from 7 German newspapers
2. **Filters** by location keywords (tiers: local → region → country)
3. **Translates** headlines + descriptions German → English via argos-translate (100% free, offline)
4. **Ranks** articles by relevance and mixes sources round-robin
5. **Outputs** a clean formatted summary

Two modes:
- **Compact** — top 5 local + 5 regional + 5 national, mixed across sources
- **Detailed** — top 5 per source per tier (full firehose)

## Quick Start (Standalone)

```bash
git clone https://github.com/asifnady/germany-news-agent.git
cd germany-news-agent
pip install -r requirements.txt
python germany_news.py
# Or for full per-source breakdown:
python germany_news.py --detailed
```

First run auto-downloads the German→English translation model (~50 MB). Subsequent runs are offline-only.

## Customizing for Your Region

Don't live in Munich? Edit **`config.json`** — no Python knowledge needed:

```json
{
  "feeds": {
    "My Local Paper": "https://example.com/rss",
    "My National Paper": "https://example.com/national/rss"
  },
  "keywords": {
    "tier1": ["my-city", "my-town", "my-neighborhood"],
    "tier2": ["my-region"],
    "tier3": ["my-country"]
  },
  "feed_boost": ["My Local Paper"]
}
```

| Setting | What it does |
|---------|-------------|
| `feeds` | RSS feed URLs and display names |
| `keywords.tier1` | Highest priority — exact matches get top billing |
| `keywords.tier2` | Regional coverage |
| `keywords.tier3` | National coverage |
| `feed_boost` | Feeds that default to tier 2 even without keyword matches |
| `compact_counts` | How many articles per section in compact mode |
| `detailed_per_source` | How many articles per source in detailed mode |

## Requirements

- Python 3.9+
- ~1.5 GB free disk (for PyTorch + translation model)
- Internet connection (first run only; model download)

## Quick Start (with OpenClaw)

1. Place the script folder on your machine
2. Set up an OpenClaw cron job:
```json
{
  "name": "germany-news-monday",
  "schedule": { "kind": "cron", "expr": "30 9 * * 1", "tz": "Europe/Berlin" },
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "Run the script and output the result: cd /path/to/germany-news-agent && python germany_news.py"
  },
  "delivery": { "mode": "announce", "channel": "discord", "to": "channel:YOUR_CHANNEL_ID" }
}
```
3. For manual triggers, tell your agent: when user says `germany news` → run compact mode; when user says `full news` → run `--detailed`

## Tech Stack

- **Python 3** — core logic
- **argos-translate** — free offline neural machine translation (German→English)
- **RSS/XML** — all data sourced from public newspaper feeds
- **Zero API costs** — no OpenAI, no DeepL, no paid services

## Project Structure

```
germany-news-agent/
├── config.json          # ← Edit this for your region
├── germany_news.py      # Main script (no hardcoded values)
├── requirements.txt     # Python dependencies
└── .gitignore
```
