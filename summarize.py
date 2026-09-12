"""
Germany News Agent — On-demand article scraping + summarization.

Usage:
    python summarize.py <url> [short|detailed|bullet|translate]

Pipeline (stdlib only — no trafilatura/lxml/torch/BART, which Windows Smart
App Control blocks on this machine since 2026-08):
    1. urllib + html.parser — scrape article text from URL
    2. online translation  — German → English (Google gtx → dict-chrome-ex → MyMemory)
    3. extractive summary  — lead + word-frequency sentence scoring

Translation has an optional third tier: when every online endpoint fails (429),
it falls back to the local ONNX engine in offline_translate.py (same Marian
family Argos used, executed by the SAC-compatible onnxruntime). After 3
consecutive online failures the run switches to offline-first for the rest of
the process, so a rate-limited run does not crawl through timeouts.

Rebuilt 2026-08-31: old pipeline (trafilatura scrape, Argos offline NMT,
DistilBART) is dead because SAC blocks lxml.etree and torch shm.dll.
"""
import argparse, sys, os, re, json, ssl, time, html as html_lib
import urllib.request, urllib.parse
from html.parser import HTMLParser
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ssl_ctx = ssl.create_default_context()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


# --- Scraping (stdlib) ---

class _TextExtractor(HTMLParser):
    """Collect <p> paragraph text; skip nav/script/style/figure noise."""
    SKIP = {"script", "style", "noscript", "nav", "footer", "aside", "form",
            "svg", "figure", "figcaption", "header", "iframe", "button"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paras = []
        self._cur = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "p":
            self._cur = []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "p":
            txt = " ".join("".join(self._cur).split())
            if txt:
                self.paras.append(txt)
            self._cur = []

    def handle_data(self, data):
        if not self._skip_depth:
            self._cur.append(data)


def _fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=25) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def scrape_article(url):
    """Fetch and extract article text; returns (title, body) or (None, None)."""
    print(f"  [scrape] Fetching: {url}", file=sys.stderr)
    try:
        page = _fetch(url)
    except Exception as e:
        print(f"  [scrape error] {e}", file=sys.stderr)
        return None, None

    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    title = html_lib.unescape(m.group(1)).strip() if m else ""

    parser = _TextExtractor()
    try:
        parser.feed(page)
    except Exception as e:
        print(f"  [scrape parse error] {e}", file=sys.stderr)
    paras = parser.paras

    if len(paras) < 2:
        # Fallback: strip tags and split into sizable blocks
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page,
                      flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text)
                  if len(b.strip()) > 80]
        paras = blocks[:20]

    body = "\n\n".join(paras)
    return title, body


# --- Translation (online fallback, same as germany_news.py) ---

_translate_cache = {}

# --- optional offline tier (see offline_translate.py) ---------------------
_offline_state = {"checked": False, "ok": False}
ONLINE_TRIP = 3          # consecutive online failures before going offline-first
_online_fail_streak = 0


def _offline_available():
    if not _offline_state["checked"]:
        _offline_state["checked"] = True
        try:
            import offline_translate as off
            _offline_state["ok"] = off.available()
            print(f"  [translate] offline ONNX engine: "
                  f"{'ready' if _offline_state['ok'] else off._state.get('why')}",
                  file=sys.stderr)
        except Exception as e:
            _offline_state["ok"] = False
            print(f"  [translate] offline engine unavailable: {e}", file=sys.stderr)
    return _offline_state["ok"]


def _offline_translate(text):
    """Last-resort local translation. Returns None if the engine can't help."""
    if not _offline_available():
        return None
    try:
        import offline_translate as off
        out = off.translate(text)
        if out:
            print("  [translate] used offline ONNX fallback", file=sys.stderr)
            return out
    except Exception as e:
        print(f"  [translate] offline fallback failed: {e}", file=sys.stderr)
    return None


def _online_translate(text):
    """Translate via free online APIs; returns translated text or None."""
    q = urllib.parse.quote(text)
    # 1) Google gtx (no key)
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=de&tl=en&dt=t&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = "".join(seg[0] for seg in data[0] if seg and seg[0])
        if out:
            return out
    except Exception as e:
        print(f"  [translate error] Google gtx: {e}", file=sys.stderr)
    # 1b) Google dict-chrome-ex (different frontend, often not rate-limited)
    try:
        url = f"https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=de&tl=en&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = data[0] if isinstance(data, list) and data else None
        if out:
            return out
    except Exception as e:
        print(f"  [translate error] Google dict-chrome-ex: {e}", file=sys.stderr)
    # 2) MyMemory (free, no key; ~500 char limit per request)
    try:
        url = f"https://api.mymemory.translated.net/get?q={q}&langpair=de|en"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = (data.get("responseData") or {}).get("translatedText")
        if out and not out.startswith("MYMEMORY WARNING"):
            return out
    except Exception as e:
        print(f"  [translate error] MyMemory: {e}", file=sys.stderr)
    return None


def _chunks(text, size=450):
    """Split text into ~size-char chunks on paragraph/sentence boundaries
    (MyMemory free tier caps at ~500 chars, so keep chunks small)."""
    chunks = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= size:
            chunks.append(para)
            continue
        sents = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„\"])", para)
        cur = ""
        for s in sents:
            if len(cur) + len(s) > size and cur:
                chunks.append(cur)
                cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur:
            chunks.append(cur)
    return chunks


def translate(text):
    """DE→EN. Online chain first; local ONNX engine once the online tier trips."""
    global _online_fail_streak
    if not text or not text.strip():
        return ""
    offline_first = _online_fail_streak >= ONLINE_TRIP and _offline_available()
    if offline_first:
        print("  [translate] online tier tripped — trying offline engine first",
              file=sys.stderr)
    out_parts = []
    for c in _chunks(text):
        key = c.strip()
        if key in _translate_cache:
            out_parts.append(_translate_cache[key])
            continue
        t = _offline_translate(c) if offline_first else None
        used_online = False
        if t is None:
            t = _online_translate(c)
            if t is None:
                _online_fail_streak += 1
            else:
                _online_fail_streak = 0
                used_online = True
        if t is None:
            t = _offline_translate(c)
        if t is None:
            t = c  # keep the German chunk rather than lose content
            print("  [translate] kept German chunk (all engines failed)",
                  file=sys.stderr)
        else:
            _translate_cache[key] = t
            if used_online:
                time.sleep(0.25)  # be polite to the free endpoints
        out_parts.append(t)
    return "\n\n".join(out_parts)


# --- Extractive summarization (replaces BART) ---

_STOP = set("""der die das den dem des ein eine einen einem einer und oder aber
als mit von zu bei fur für auf an aus um über unter nach vor zwischen im in
ist sind war waren wird wurde werden hat haben hatte nicht doch ja nein nur
auch noch schon sehr viel viele dass das die den""".split())


def _split_sentences(text):
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
            if len(s.strip()) > 15]


def _word_freq(sents):
    words = [w.lower() for s in sents
             for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", s)
             if w.lower() not in _STOP]
    cnt = Counter(words)
    mx = max(cnt.values()) if cnt else 1
    return {w: c / mx for w, c in cnt.items()}


def summarize(text, level="detailed"):
    """Extractive summary: lead sentences weighted by word-frequency score."""
    sents = _split_sentences(text)
    if not sents:
        return "Article text too short to summarize."
    n = {"short": 2, "detailed": 5, "bullet": 8}.get(level, 5)
    freq = _word_freq(sents)
    scored = []
    for i, s in enumerate(sents):
        lead = 1.0 - (i / max(len(sents), 1)) * 0.6  # earlier = stronger lead
        fw = [freq.get(w.lower(), 0)
              for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", s)
              if w.lower() not in _STOP]
        fs = (sum(fw) / len(fw)) if fw else 0.0
        scored.append((lead * 0.65 + fs * 0.35, i, s))
    scored.sort(key=lambda t: t[0], reverse=True)
    picked = [s for _, _, s in sorted(scored[:n], key=lambda t: t[1])]
    if level == "bullet":
        return "\n• " + "\n• ".join(picked)
    return " ".join(picked)


# --- Main CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Scrape, translate, and summarize a German news article.")
    parser.add_argument("url", help="Article URL to scrape and summarize")
    parser.add_argument("level", nargs="?", default="detailed",
                        choices=["short", "detailed", "bullet", "translate"],
                        help="Summary detail level, or 'translate' for the full English translation (default: detailed)")
    args = parser.parse_args()

    print("Article summarization started...", file=sys.stderr)

    print("  Step 1/3: Scraping article...", file=sys.stderr)
    title, raw_text = scrape_article(args.url)
    if not raw_text:
        print("ERROR: Could not scrape article from URL. The site may be "
              "blocking requests or the link may be broken.")
        sys.exit(1)
    print(f"  Scraped {len(raw_text)} characters of German text.", file=sys.stderr)

    print("  Step 2/3: Translating German→English (online)...", file=sys.stderr)
    en_text = translate(raw_text)
    print(f"  Translated to {len(en_text)} characters of English.", file=sys.stderr)

    if args.level == "translate":
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                f"translation_{ts}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(en_text)
        print(f"\n{'─' * 60}", file=sys.stderr)
        print(f"  Full translation saved to: {out_path}", file=sys.stderr)
        print(f"  Size: {len(en_text)} characters", file=sys.stderr)
        print(f"{'─' * 60}", file=sys.stderr)
        print(out_path)
    else:
        print(f"  Step 3/3: Summarizing (extractive, {args.level})...",
              file=sys.stderr)
        summary = summarize(en_text, args.level)
        print(f"\n{'─' * 60}")
        if title:
            print(f"**{title}**")
        print(summary)
        print(f"{'─' * 60}")


if __name__ == "__main__":
    main()
