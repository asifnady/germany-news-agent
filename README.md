# Germany News Agent 🐅

A Python tool that fetches German news from RSS feeds, translates them to English (offline, free), and delivers curated summaries to Discord or terminal — with on-demand article summarization via DistilBART.

Zero API costs. Fully offline after first setup.

## Features

- **Fetches** RSS feeds from 7 German news sources (SZ, FAZ, Bild, Merkur, Presseportal)
- **Filters** by location keywords across three tiers: local → regional → national
- **Translates** headlines + full articles German → English via argos-translate (100% free, offline)
- **Ranks & mixes** round-robin across sources for balanced coverage
- **On-demand summarization** — scrape any article URL, translate to English, summarize with DistilBART
- **Discord integration** — trigger via simple commands

## Modes

| Mode | Command | What it does |
|------|---------|-------------|
| Compact | `germany news` | Top 5 local + 5 regional + 5 national headlines (flat-numbered) |
| Detailed | `full news` | Per-source breakdown, top 5 per source per tier (flat-numbered) |
| Summarize | `@Tipu <number> [short\|detailed\|bullet]` | Scrape + translate + BART summarize a specific article |

### Summary Levels

| Qualifier | Length | Format |
|-----------|--------|--------|
| `short` | 1-2 sentences | Gist |
| `detailed` (default) | 3-5 sentences | Paragraph |
| `bullet` | Key points | Bullet list |

## Quick Start (Standalone)

```bash
git clone https://github.com/asifnady/germany-news-agent.git
cd germany-news-agent
pip install -r requirements.txt
python germany_news.py
# Or for full per-source breakdown:
python germany_news.py --detailed
```

First run auto-downloads the German→English translation model (~50 MB). Subsequent runs are fully offline.

### On-Demand Summarization

```bash
# Scrape, translate, and summarize any German article URL
python summarize.py "https://www.sueddeutsche.de/muenchen/example" detailed
python summarize.py "https://example.com/artikel" short
python summarize.py "https://example.com/artikel" bullet
```

First `summarize.py` call downloads DistilBART (~380 MB). Subsequent calls are instant.

## Customizing for Your Region

Don't live in Munich? Edit **`config.json`** — no Python knowledge needed:

```json
{
  "feeds": {
    "My Local Paper": "https://example.com/rss"
  },
  "keywords": {
    "tier1": ["my-city", "my-town"],
    "tier2": ["my-region"],
    "tier3": ["my-country"]
  },
  "feed_boost": ["My Local Paper"]
}
```

| Setting | What it does |
|---------|-------------|
| `feeds` | RSS feed URLs and display names |
| `keywords.tier1` | Highest priority — exact keyword matches get top billing |
| `keywords.tier2` | Regional coverage |
| `keywords.tier3` | National coverage |
| `feed_boost` | Feeds that default to tier 2 even without keyword matches |
| `compact_counts` | How many articles per section in compact mode |
| `detailed_per_source` | How many articles per source in detailed mode |

## Requirements

- Python 3.9+
- ~2 GB free disk (PyTorch + translation model + DistilBART)
- Internet connection (first run only; model downloads)

## Project Structure

```
germany-news-agent/
├── config.json              # 🎯 Edit this for your region
├── germany_news.py          # Main script (fetch, filter, translate, output + article mapping)
├── summarize.py             # On-demand: scrape + translate + DistilBART summarization
├── requirements.txt         # Python dependencies
├── DESIGN.md                # Architecture decisions & design docs
├── last_news_articles.json  # Runtime: flat numbered article map (auto-generated, gitignored)
├── README.md                # This file
└── .gitignore
```

## Tech Stack

- **Python 3** — core logic
- **argos-translate** — free offline neural machine translation (German→English)
- **trafilatura** — article text extraction from URLs
- **sshleifer/distilbart-cnn-6-6** — distilled BART summarization (306M params, CPU-friendly)
- **RSS/XML** — all data sourced from public newspaper feeds
- **Zero API costs** — no OpenAI, no DeepL, no paid services

## Discord / OpenClaw Integration

1. Place the script folder on your machine
2. Set up an OpenClaw cron job for scheduled news:
```json
{
  "name": "germany-news-monday",
  "schedule": { "kind": "cron", "expr": "30 9 * * 1", "tz": "Europe/Berlin" },
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "cd C:\\path\\to\\germany-news-agent && python germany_news.py"
  },
  "delivery": { "mode": "announce", "channel": "discord", "to": "channel:YOUR_CHANNEL_ID" }
}
```
3. Configure trigger handlers:
   - `germany news` → compact mode
   - `full news` → detailed mode  
   - `@Tipu <number>` → scrape + summarize that article

## Architecture

See [DESIGN.md](DESIGN.md) for full architecture decisions, data flow diagrams, and design rationale.

## License

MIT — do what you want with it.
