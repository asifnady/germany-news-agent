# Germany News Agent 🐅

Fetches German news from RSS feeds, filters it by *your* location tiers, translates it to English with free online services, and serves it as a self-hosted reading page on your local network — plus optional Discord delivery if you run it under OpenClaw.

**No API keys. No paid services. No build step.**

---

## What you get

- A clean, mobile-first reading page (headlines grouped **Local / Bavaria / Germany**)
- Tap a headline → English summary; **"Full EN translation"** button → whole article translated on demand
- Day navigation — keeps the last 30 days
- A **Settings tab** in the page — edit `config.json` (feeds + location tiers) from any device, **Save** (keeps a backup) and **Rebuild now** to refetch with your settings
- Optional: Discord posts and `@Tipu <number>` on-demand article summaries (OpenClaw integration)

---

## Requirements

- **Python 3.9+** — the pipeline is **pure standard library**, so there is nothing to `pip install`
- **Node.js 18+** — the web server is zero-dependency (no `npm install`)
- Internet access — RSS feeds and translation both happen online
- *(Optional)* `numpy`, `onnxruntime`, `tokenizers` + the ~106 MB model — only if you want the offline translation fallback

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

### Third tier: the offline engine

When all three endpoints fail, translation falls back to a **local ONNX model** (`offline_translate.py`) — the same Marian/Opus-MT family Argos used, executed by `onnxruntime` instead of CTranslate2. This exists because some hosts (Windows with Smart App Control in Enforcement mode) block the unsigned native DLLs behind `ctranslate2` / `torch` / `sentencepiece`; `onnxruntime` and `tokenizers` are signed and load fine.

```bash
python tools/fetch_offline_model.py        # ~106 MB into models/opus-mt-de-en/ (not in git)
pip install numpy onnxruntime tokenizers   # optional — the pipeline runs without them
```

Behaviour: after **3 consecutive online failures** the run switches to offline-first, so a rate-limited build doesn't crawl through timeouts. Measured on an i3-8100: **0.6–2.3 s per sentence**, no network, no API key. Quality is excellent on headlines and straight sentences; on long, clause-heavy articles it is noticeably rougher than the online tier — which is exactly why it's the fallback and not the default.

Verify it end to end: `python tools/test_offline_fallback.py` (forces the online tier down and asserts English comes back).

> Design note: beam search was tried and rejected. It produced identical output on simple sentences and only marginal gains on hard ones, at ~56 s per sentence — the non-merged decoder recomputes the whole prefix each step. Greedy is the right trade-off here.

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

### Editing the config from the page (no editor needed)

The **Settings** tab in the reader edits `config.json` directly:

1. Open the page → **Settings** (works from your phone too).
2. Change the JSON — set your own `feeds` and `tier1` / `tier2` / `tier3` keywords.
3. **Save** — the server validates it and keeps the previous version as `config.json.bak`.
4. **Rebuild now** — runs `web_build.py` in the background (~1–2 min) and the page switches back to Headlines with your new region.

Guardrails: the server rejects a config that is not an object, or whose `feeds` / `keywords` have the wrong shape — so a typo cannot silently break the daily build. The API is `GET /api/config`, `POST /api/config`, `POST /api/rebuild`, `GET /api/rebuild`.

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
├── offline_translate.py     # offline DE→EN engine (onnxruntime) — last-resort fallback
├── tools/
│   ├── fetch_offline_model.py    # downloads the ~106 MB ONNX model
│   └── test_offline_fallback.py  # proves the fallback engages
├── models/                  # model files (gitignored, fetched on demand)
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
