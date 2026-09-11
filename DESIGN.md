# Germany News Agent — Design Doc v3 (current: Windows PC) 🐯

> Updated: 2026-09-11 · Status: running in production on Asif's PC
> Audience: future-me (Tipu) after a context reset / OpenClaw update.
> Supersedes **v2** (2026-06-11, Pakistan-laptop era, Argos+BART stack) — v2 is in git history, its stack is **dead** on this machine.

---

## 0. Memory map — read these first

| Layer | File | What's in it |
|---|---|---|
| Channel state | `~/.openclaw/workspace/memory/channels/germany-news-daily.md` | Purpose, standing items, open questions |
| Global brain | `~/.openclaw/workspace/MEMORY.md` | Sub-Memory Index + global rules |
| Run commands + quirks | `~/.openclaw/workspace/TOOLS.md` → "Germany News Agent (rebuilt 2026-08-19)" | Exact commands, SAC/MSVC notes |
| This repo | `DESIGN.md` (here) · `README.md` (public usage) | Architecture + how-to |

Rule: channel memory holds *state*, TOOLS.md holds *commands*, this file holds *design*. Don't duplicate across them.

---

## 1. What it does

Fetches German news from RSS feeds → filters by location tier → translates DE→EN → delivers. Zero API cost, no paid services. Three delivery surfaces today:

1. **Internal WLAN web page** ← primary reading surface (since 2026-09-06)
2. **Discord on-demand** — `@Tipu <number> [short|detailed|bullet]` article summaries

The former **weekly Discord digest** (Mon 09:00) was **retired 2026-09-11** — the page made it redundant and its last run failed on message delivery.

---

## 2. Architecture (current)

```
RSS feeds (7, config.json)
        │  urllib
        ▼
germany_news.fetch_feed() ──► tier filter (keywords tier1-3) ──► pick_mixed() round-robin
        │
        ├─► web_build.py  : translate title+desc, write web/data/*.json   ← daily 07:00
        │        └─ summarize.translate()  (cache: web/data/cache.json)
        │
        └─► germany_news.py : Discord/terminal text output + last_news_articles.json  ← manual / weekly
                                    │
                                    ▼
                        web/server.js (zero-dep Node, :8090)
                          serves public/index.html + /api/*
                          on demand runs summarize.py <url> translate  (job queue, page polls)
```

**Two entry scripts share one fetch/filter core** (`germany_news.py` is imported by `web_build.py` — don't refactor it away).

---

## 3. Surfaces

### 3a. Web reader (primary)
- URL: `http://192.168.2.217:8090` (LAN) · `http://localhost:8090` (host). Binds `0.0.0.0`.
- Flow: headlines → tap for EN summary → "Full EN translation" button → server queues `summarize.py <url> translate`, page polls `/api/translate` until done.
- Finished translations cached in `web/data/translations/` — **never retranslated**.
- Auto-starts at logon via Startup VBS: `web/start-germany-news-web.vbs` (manual: `web/start-server.cmd`). Log: `web/server.log`.

### 3b. Discord on-demand
- `germany news` → compact (5 local / 5 bavaria / 5 germany)
- `full news` → `--detailed` (per-source breakdown)
- `@Tipu <number> [short|detailed|bullet]` → looks up `last_news_articles.json` → runs `summarize.py <url> <mode>` (default `detailed`)

### 3c. Discord weekly digest — RETIRED 2026-09-11
- Cron `germany-news-weekly` (Mon 09:00) was **removed** at Asif's request. `germany_news.py` still works manually if a digest is ever wanted again.
- To recreate: isolated agentTurn, `0 9 * * 1` Europe/Berlin, run `germany_news.py`, post stdout to #germany-news-daily in <1900-char chunks.

---

## 4. Why everything is stdlib-only now (important)

Windows **Smart App Control** is in Enforcement mode (`VerifiedAndReputablePolicyState=1`) and blocks unsigned native DLLs. Killed:
- `sentencepiece` / `ctranslate2` → **Argos offline translation dead**
- `lxml.etree` → **trafilatura scraping dead**
- `torch shm.dll` → **DistilBART summarization dead**

Response:
- `germany_news.py` guards the Argos import → falls back to **online translation** (cache + 0.25 s politeness delay).
- `summarize.py` was **rebuilt as pure stdlib** (urllib + html.parser scrape, online translate, extractive lead+word-freq summary). No lxml/torch.
- Translation chain everywhere: **Google gtx → Google dict-chrome-ex (`clients5.google.com`) → MyMemory**.
- **Don't re-enable local models** without signing the DLLs or disabling SAC (Asif's call).

MSVC quirk: the venv's `sitecustomize.py` registers `_runtime_dlls` (from pip `msvc-runtime`) because the PC lacks VC++ redistributable. **Don't delete it.**

---

## 5. File map

```
germany-news-agent/
├── config.json              # feeds, tier keywords, counts — EDIT THIS to retune
├── germany_news.py          # fetch + filter + rank + Discord text + mapping core
├── web_build.py             # daily build → web/data/*.json (+ persistent EN cache)
├── summarize.py             # on-demand: stdlib scrape + online translate + summary
├── setup.py                 # interactive onboarding wizard (stdlib only)
├── last_news_articles.json  # number → article map for @Tipu <number> (mode: "web")
├── web/
│   ├── server.js            # zero-dep Node server, :8090, job queue for translations
│   ├── public/index.html    # the reader UI (no build step)
│   ├── data/news/<date>.json# one file per day (kept 30 days, pruned)
│   ├── data/latest.json     # copy of newest day
│   ├── data/days.json       # date index (newest first)
│   ├── data/cache.json      # persistent DE→EN cache (repeated stories cost nothing)
│   ├── data/translations/   # finished full translations
│   ├── start-server.cmd · start-germany-news-web.vbs · server.log
├── phase1_fetch.py · phase2_filter.py · phase3_translate_test.py  # legacy phase tests
└── README.md · DESIGN.md · requirements.txt · .gitignore
```

---

## 6. Crons (OpenClaw, `sessionTarget: isolated`)

| Job | Schedule | Does |
|---|---|---|
| `germany-news-daily` | `0 7 * * *` Europe/Berlin | Silent `web_build.py`. **No message on success** (`delivery.mode: none`); error alert → #germany-news-daily. `failureAlert.after: 1`. |
| ~~`germany-news-weekly`~~ | ~~`0 9 * * 1`~~ | **Retired 2026-09-11** (redundant with the web page). |

---

## 7. Run commands (PowerShell)

```powershell
cd C:\Users\anade\projects\germany-news-agent
$env:PYTHONIOENCODING='utf-8'

.venv\Scripts\python.exe web_build.py                    # daily web build (manual)
.venv\Scripts\python.exe germany_news.py                 # compact Discord/terminal text
.venv\Scripts\python.exe germany_news.py --detailed      # per-source breakdown
.venv\Scripts\python.exe summarize.py "<url>" [short|detailed|bullet|translate]
```

---

## 8. Section caps (tune in `web_build.py` → `SECTIONS`)

`LOCAL (FFB Region)` tiers {1,2} cap **12** · `BAVARIA` tier {3} cap **7** · `GERMANY` tier {4} cap **7** · `FETCH_PER_FEED = 15`.

`config.json` tunables: `feeds`, `keywords.tier1/2/3`, `feed_boost`, `compact_counts`, `detailed_per_source`.
Boosts: **SZ FFB** + **Merkur FFB** (Asif lives in Germering, Landkreis Fürstenfeldbruck).

---

## 9. Edge cases / error handling

| Scenario | Handling |
|---|---|
| Zero articles fetched | `web_build.py` exits non-zero, **previous day's data untouched** (by design) |
| Translation endpoint 429 | Falls through chain gtx → dict-chrome-ex → MyMemory; caches only successful results |
| All endpoints fail | Original German text returned (never empty/crash) |
| `last_news_articles.json` missing | Reply: "No recent news found — run `germany news`/`full news` first" |
| Article # out of range | Reply: "Article #X not found — valid numbers: 1-N" |
| Repeated build same date | Overwrites that day's file; days older than 30 pruned |
| Translation of same article twice | Served from `web/data/translations/` cache |

---

## 10. Post-update pickup checklist

1. Read `memory/channels/germany-news-daily.md` + `TOOLS.md` → "Germany News Agent".
2. Confirm web server up: `http://localhost:8090/api/health` (returns running-job count).
3. Confirm cron `germany-news-daily` ran today (status `ok`, duration ~95 s).
4. If the page is stale: run `web_build.py` manually, check `web/server.log`.
5. Don't touch `_runtime_dlls` / `sitecustomize.py`; don't re-add Argos/BART.

---

## 11. Open items

- WLAN IP `192.168.2.217` is hardcoded in `web/server.js` display. **DHCP reservation requested 2026-09-11** (router `192.168.2.1`, WLAN adapter MAC `60-F2-62-CE-B0-12`) — pending Asif doing it in the router UI.
- Translation endpoints are unofficial/fragile; if all three 429 for long, consider a keyed free tier.
- ✅ Done 2026-09-11: `summarize.py` committed (`22dd975`); weekly digest retired.

## 12. Repo hygiene

Work tree is clean as of `22dd975`. Commit before/after working on this repo; it has a GitHub remote but changes are **not pushed** automatically.

---

## 13. Historical (v2, Pakistan laptop) — dead stack

`trafilatura` scrape + `argos-translate` (offline DE→EN) + `sshleifer/distilbart-cnn-6-6` (~380 MB) + phase test scripts + interactive `setup.py` wizard. Design rationale tables are preserved in git history (`git show 1d2c0e0:DESIGN.md`). Kept in the repo only as legacy phase scripts; **not used at runtime**.
