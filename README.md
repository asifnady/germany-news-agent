# Germany News Agent 🐅

Fetches German news from RSS feeds, filters it by *your* location tiers, translates it to English with free online services, and serves it as a self-hosted reading page on your local network — plus optional Discord delivery if you run it under OpenClaw.

**No API keys. No paid services. No build step.**

---

## What you get

- A clean, mobile-first reading page (headlines grouped **Local / Bavaria / Germany**)
- Tap a headline → English summary; **"Full EN translation"** button → whole article translated on demand
- Day navigation — keeps the last 30 days
- Optional: Discord posts and `@Tipu <number>` on-demand article summaries (OpenClaw integration)

---

## Requirements

- **Python 3.9+** — the pipeline is **pure standard library**, so there is nothing to `pip install`
- **Node.js 18+** — the web server is zero-dependency (no `npm install`)
- Internet access — RSS feeds and translation both happen online

---

## Quick start

```bash
git clone https://github.com/asifnady/germany-news-agent.git
cd germany-news-agent

python web_build.py      # fetch + filter + translate → writes web/data/
node web/server.js       # serve the page on port 8090
```

Then open **<http://localhost:8090>**.

`web_build.py` must run once before the page has anything to show. Run it daily (cron / Task Scheduler) and the page always has fresh news.

---

## Serving it on your local network

The server binds to `0.0.0.0:8090`, so it is reachable from **any device on your LAN** — phone, tablet, TV browser — as soon as it is running.

**1. Find the host's LAN IP**

| OS | Command |
|---|---|
| Windows | `ipconfig` → *IPv4 Address* |
| Linux | `hostname -I` |
| macOS | `ipconfig getifaddr en0` |

**2. Open the page from your phone**

```
http://<LAN-IP>:8090          e.g. http://192.168.2.217:8090
```

**3. Allow it through the firewall**

- **Windows:** the first run pops a prompt — tick *Private networks* and allow. If you missed it: *Firewall → Allow an app → Node.js*.
- **Linux:** `sudo ufw allow 8090/tcp`
- **macOS:** usually allowed by default on the same network.

**4. Keep the address stable**

Ask your router for a **DHCP reservation** for this machine (bind its MAC to a fixed IP). Otherwise the URL changes when the lease renews — and any bookmark, phone shortcut, or script breaks.

**5. Start it automatically**

| OS | How |
|---|---|
| Windows | shortcut in `shell:startup` → `web\start-server.cmd` (a hidden-VBS launcher is included) |
| Linux | systemd user unit with `ExecStart=/usr/bin/node /path/web/server.js` |
| macOS | a `launchd` plist |

**6. Notes**

- **No authentication.** It is a LAN convenience page. Never port-forward it to the internet.
- Change the port: `PORT=8091 node web/server.js`
- Logs (Windows launcher): `web/server.log`

---

## Translation: the free online services

The whole system is built around three **free, key-less translation endpoints**, tried in order:

| # | Service | Endpoint | Notes |
|---|---|---|---|
| 1 | Google gtx | `translate.googleapis.com/translate_a/single?client=gtx` | best quality, rate-limits first |
| 2 | Google dict-chrome-ex | `clients5.google.com/translate_a/t?client=dict-chrome-ex` | different frontend, often survives when gtx 429s |
| 3 | MyMemory | `api.mymemory.translated.net/get` | anonymous quota, ~500 chars/request |

How it behaves:

- **Chunking** — long text is split into ~450-character chunks on paragraph/sentence boundaries (MyMemory's limit), translated piece by piece, then rejoined.
- **Caching** — every successful translation is stored. `web/data/cache.json` holds headlines/summaries; `web/data/translations/` holds finished full articles. Nothing is ever translated twice, so repeat reading costs zero requests.
- **Politeness** — a 0.25 s pause between calls keeps all three endpoints friendly.
- **Rate limits** — `HTTP 429` from any endpoint is normal under heavy use. The chain immediately falls through to the next one. If all three fail, the **German text is kept** rather than dropping content.
- **Want a guaranteed provider?** `translate()` in `summarize.py` is the single choke point used by both the daily build and on-demand translation — swap in a keyed API (DeepL, Google Cloud Translate) there and nothing else changes.

---

## Customize it for your region

Everything is driven by **`config.json`** — no Python knowledge required:

```json
{
  "feeds": { "My Local Paper": "https://example.com/rss" },
  "keywords": {
    "tier1": ["my-town", "my-district"],
    "tier2": ["my-city", "my-region"],
    "tier3": ["my-state"]
  },
  "feed_boost": ["My Local Paper"]
}
```

| Setting | What it does |
|---|---|
| `feeds` | RSS feed URLs and display names |
| `keywords.tier1` | Your town / district — highest priority |
| `keywords.tier2` | Your city / surrounding region |
| `keywords.tier3` | Your state / country |
| `feed_boost` | Local papers promoted a tier even without a keyword hit |
| `compact_counts` | Articles per section in Discord compact mode |
| `detailed_per_source` | Articles per source in Discord detailed mode |

Section sizes for the web page live in `web_build.py` → `SECTIONS` (`LOCAL` 12, `BAVARIA` 7, `GERMANY` 7) and `FETCH_PER_FEED`.

---

## On-demand summaries (CLI)

```bash
python summarize.py "<article-url>" short      # 1-2 sentences
python summarize.py "<article-url>" detailed   # 3-5 sentences (default)
python summarize.py "<article-url>" bullet     # key points
python summarize.py "<article-url>" translate  # full English text → translation_*.txt
```

---

## Optional: Discord / OpenClaw integration

- `@Tipu <number> [short|detailed|bullet]` → scrapes and summarizes a numbered article from the last run
- A daily job can rebuild the page silently and alert you only on failure
- `python setup.py` walks through workspace path, channel, and schedule for a fresh install

---

## Project structure

```
germany-news-agent/
├── config.json              # 🎯 edit this for your region
├── germany_news.py          # fetch + filter + rank core, Discord/terminal output
├── web_build.py             # daily build → web/data/*.json (+ translation cache)
├── summarize.py             # scrape + translate + summarize one article (stdlib)
├── web/
│   ├── server.js            # zero-dep Node server — page + API on :8090
│   ├── public/index.html    # the reader UI
│   ├── start-server.cmd     # Windows launcher
│   ├── start-germany-news-web.vbs
│   └── data/                # generated: news/<date>.json, latest.json, days.json,
│                            #   cache.json, translations/   (gitignored)
├── setup.py                 # onboarding wizard for OpenClaw users
├── DESIGN.md                # architecture + design decisions
├── requirements.txt         # empty by design (stdlib pipeline)
└── LICENSE                  # MIT
```

---

## Legacy: the old offline stack

v2 of this tool ran fully offline using `argos-translate` (neural MT) + `trafilatura` (scraping) + `DistilBART` (summarization). On Windows with **Smart App Control in Enforcement mode**, those native DLLs (`sentencepiece`, `ctranslate2`, `lxml.etree`, `torch`) are blocked and the stack cannot load.

The current pipeline replaces all three with stdlib scraping, online translation, and extractive summarization. The old dependencies remain listed (commented) in `requirements.txt` for anyone on a machine that allows them — see DESIGN.md for the full story.

---

## License

MIT — do what you want with it.
