# Germany News Agent — Design Lock v2 🐅

> Date: 2026-06-11
> Status: Implemented

---

## 1. Overview

A Python-based tool that fetches German news from RSS feeds, filters by location, translates to English, and delivers curated summaries to Discord. **v2 adds on-demand article scraping + DistilBART summarization** via user interaction.

**Triggers (from TOOLS.md):**
- `germany news` → compact mode (5 local + 5 regional + 5 national)
- `full news` → detailed mode (per-source breakdown)
- `@Tipu <number> [short|detailed|bullet]` → on-demand article scrape + summarization

---

## 2. Architecture

```
    ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
    │  RSS Feeds   │ ──►  │  Fetch +      │ ──►  │  Filter +     │
    │  (7 sources) │      │  Parse RSS    │      │  Rank by Tier │
    └──────────────┘      └──────────────┘      └──────┬───────┘
                                                        │
                                                        ▼
                                            ┌──────────────────────┐
                                            │  Output numbered     │
                                            │  article list to     │
                                            │  Discord channel     │
                                            │  (German, raw)       │
                                            └──────────┬───────────┘
                                                        │
                                            ╔═══════════╧═══════════╗
                                            ║  ON USER REQUEST     ║
                                            ║  (@Tipu <number>)    ║
                                            ╚═══════════╤═══════════╝
                                                        │
                                                        ▼
                                            ┌──────────────────────┐
                                            │  1. trafilatura:     │
                                            │     scrape article    │
                                            │     from URL          │
                                            └──────────┬───────────┘
                                                        │
                                                        ▼
                                            ┌──────────────────────┐
                                            │  2. argos-translate: │
                                            │     German → English │
                                            │     (offline, free)  │
                                            └──────────┬───────────┘
                                                        │
                                                        ▼
                                            ┌──────────────────────┐
                                            │  3. sshleifer/       │
                                            │     distilbart-      │
                                            │     cnn-6-6:         │
                                            │     Summarize (EN)   │
                                            └──────────┬───────────┘
                                                        │
                                                        ▼
                                            ┌──────────────────────┐
                                            │  4. Output summary   │
                                            │     to Discord       │
                                            └──────────────────────┘
```

---

## 3. Design Decisions (Grill Sessions)

### 3.1 Article Content Source
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scraping library | `trafilatura` | Lighter, maintained, purpose-built for article extraction |
| When to scrape | On-demand only | Scrape only the article(s) the user explicitly requests |
| Fallback on scrape failure | Use RSS description as-is (no BART) | Don't crash, just return what we have |

### 3.2 Numbering Scheme
| Decision | Choice |
|----------|--------|
| Numbering style | Flat single numbers (1, 2, 3...) across the entire output |
| Mapping file | `last_news_articles.json` — rewritten every run, maps number → article metadata |
| Persistence | Only the last session's articles; replaced next time news is fetched |

### 3.3 Trigger Mechanism
| Decision | Choice |
|----------|--------|
| Trigger format | `@Tipu <number> [qualifier]` |
| Qualifiers | `short` (1-2 sentences), `detailed` (3-5 para), `bullet` (key points) |
| Default qualifier | `detailed` if omitted |
| Scope | Only acts when mentioned — ignores bare number messages in channel |

### 3.4 Summary Model
| Decision | Choice |
|----------|--------|
| Model | `sshleifer/distilbart-cnn-6-6` (~380 MB) |
| Why this model | Distilled BART-large (6+6 layers, ~306M params). Good quality, light CPU inference, fits 8 GB RAM |
| Download | Auto-download from HuggingFace on first use |
| Language | English — full article is translated via argos-translate before summarization |

### 3.5 Language Pipeline
| Step | Tool | Input | Output |
|------|------|-------|--------|
| Fetch RSS | `urllib` | Feed URLs | German headlines + descriptions |
| Filter | Regex keywords | German article metadata | Ranked articles by tier |
| Scrape | `trafilatura` | Article URL | Full German article text |
| Translate | `argos-translate` | German text | English text |
| Summarize | `sshleifer/distilbart-cnn-6-6` | English text | English summary |

---

## 4. Data Flow: `@Tipu <number>`

1. User triggers `full news` or `germany news` → script runs, posts numbered article list to Discord
2. Script saves `last_news_articles.json`:
```json
{
  "timestamp": "2026-06-11T22:00:00+05:00",
  "mode": "compact",
  "articles": {
    "1": { "source": "SZ FFB", "title": "...", "url": "https://...",
           "rss_desc": "..." },
    "2": { ... },
    ...
  }
}
```
3. User replies: `@Tipu 5 detailed`
4. Agent reads `last_news_articles.json`, finds article #5
5. Agent runs `python summarize.py "<url>" detailed`:
   - `trafilatura` scrapes full text from URL
   - `argos-translate` translates German → English
   - `sshleifer/distilbart-cnn-6-6` summarizes English text (detail level depends on qualifier)
6. Agent posts summary to Discord

---

## 5. File Structure

```
germany-news-agent/
├── config.json              # Feeds, keywords, tier config
├── germany_news.py          # Main script (fetch, filter, translate, output + mapping)
├── summarize.py             # On-demand: trafilatura scrape + translate + DistilBART
├── setup.py                 # Interactive setup wizard for new users
├── last_news_articles.json  # Runtime: flat numbered article map (auto-generated)
├── phase1_fetch.py          # Phase test: fetch RSS feeds only
├── phase2_filter.py         # Phase test: filter + rank articles
├── phase3_translate_test.py # Phase test: argos-translate setup
├── requirements.txt         # Python dependencies
├── README.md                # Usage docs + setup wizard instructions
├── DESIGN.md                # This file
├── .gitignore
```

---

## 6. Dependencies

```txt
argostranslate==1.11.0
ctranslate2==4.8.0
sentencepiece==0.2.1
sacremoses==0.1.1
trafilatura                # Article text extraction
transformers               # DistilBART model
torch                      # PyTorch (CPU)
```

*(No additional deps for setup.py — it uses only stdlib.)*

| Resource | Size | When |
|----------|------|------|
| argos-translate model | ~50 MB | First run (already installed) |
| distilbart-cnn-6-6 | ~380 MB | First `@Tipu` trigger |
| Per-summary runtime | ~5-15s CPU | Each trigger |

---

## 7. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| `last_news_articles.json` missing | Reply: "No recent news found — run `germany news` or `full news` first" |
| Article number out of range | Reply: "Article #X not found — valid numbers: Y-Z" |
| Scrape fails (403/blocked) | Return RSS description as-is (no BART summary) |
| BART model not yet cached | Auto-downloads on first call (~380 MB, ~1-2 min) |
| BART inference fails | Return translated full text instead |
| Trigger without number | Reply with usage: `@Tipu <number> [short|detailed|bullet]` |

---

## 8. Summary Level Definitions

| Qualifier | Max Length | Min Length | Format |
|-----------|-----------|-----------|--------|
| `short` | 60 | 15 | 1-2 sentence gist |
| `detailed` (default) | 150 | 40 | 3-5 sentence paragraph |
| `bullet` | 180 | 50 | Detailed summary split into bullet points |

---

## 9. Testing Status

- ✅ `germany_news.py` compact mode — fetches, filters, numbers, saves mapping
- ✅ `germany_news.py` detailed mode — same with per-source breakdown
- ✅ `summarize.py` scraping — trafilatura extracts article text from SZ/FAZ/etc.
- ✅ `summarize.py` translation — argos-translate DE→EN working
- ✅ `summarize.py` BART — distilbart-cnn-6-6 loaded and tested
