"""
Germany News Agent — On-demand article scraping + BART summarization.

Usage:
    python summarize.py <url> [short|detailed|bullet]

Pipeline:
    1. trafilatura — scrape full article text from URL
    2. argos-translate — German → English translation (offline)
    3. facebook/bart-base-cnn — English summarization (offline)

First run will download the Hugging Face model (~600 MB).
"""
import argparse, sys, os, warnings
warnings.filterwarnings("ignore")

# --- Translation (reuse argos-translate logic from germany_news.py) ---
import argostranslate.package, argostranslate.translate

_translator_ready = False
def setup_translator():
    global _translator_ready
    if _translator_ready:
        return
    # Check if de→en translation works (model already on disk)
    try:
        test = argostranslate.translate.translate("Hallo", "de", "en")
        _translator_ready = True
        return
    except Exception:
        pass
    # Need to download and install
    print("  [setup] Downloading German→English translation model...", file=sys.stderr)
    argostranslate.package.update_package_index()
    for pkg in argostranslate.package.get_available_packages():
        if pkg.from_code == "de" and pkg.to_code == "en":
            download_path = pkg.download()
            argostranslate.package.install_from_path(download_path)
            _translator_ready = True
            return

def translate(text):
    if not text or not text.strip():
        return ""
    try:
        return argostranslate.translate.translate(text, "de", "en")
    except Exception as e:
        print(f"  [translate error] {e}", file=sys.stderr)
        return text


# --- Scraping via trafilatura ---
def scrape_article(url):
    """Fetch and extract article text from a URL using trafilatura."""
    import trafilatura
    print(f"  [scrape] Fetching: {url}", file=sys.stderr)
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded, output_format="txt", favor_precision=True,
                                    include_comments=False, include_tables=False,
                                    include_images=False, include_formatting=False)
        if text:
            text = text.strip()
        return text
    except Exception as e:
        print(f"  [scrape error] {e}", file=sys.stderr)
        return None


# --- BART Summarization ---
_bart_model = None
_bart_tokenizer = None

def setup_bart():
    global _bart_model, _bart_tokenizer
    if _bart_model is not None:
        return
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    model_name = "sshleifer/distilbart-cnn-6-6"
    print(f"  [bart] Loading {model_name}...", file=sys.stderr)
    _bart_tokenizer = AutoTokenizer.from_pretrained(model_name)
    _bart_model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    print(f"  [bart] Model loaded.", file=sys.stderr)

def summarize(text, level="detailed"):
    """Summarize English text using bart-base-cnn.
    
    Args:
        text: English article text to summarize
        level: "short", "detailed", or "bullet"
    
    Returns:
        Summary string
    """
    global _bart_model, _bart_tokenizer
    if not text or len(text.strip()) < 20:
        return "Article text too short to summarize."
    
    setup_bart()
    
    # Set generation parameters based on level
    if level == "short":
        max_length = 60
        min_length = 15
    elif level == "bullet":
        max_length = 180
        min_length = 50
    else:  # detailed (default)
        max_length = 150
        min_length = 40
    
    # Truncate input if too long (BART has 1024 token limit)
    inputs = _bart_tokenizer(
        text,
        max_length=1024,
        truncation=True,
        return_tensors="pt"
    )
    
    print(f"  [bart] Generating {level} summary...", file=sys.stderr)
    summary_ids = _bart_model.generate(
        inputs["input_ids"],
        max_length=max_length,
        min_length=min_length,
        num_beams=4,
        length_penalty=2.0,
        early_stopping=True,
        no_repeat_ngram_size=3,
    )
    
    summary = _bart_tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    
    # Post-process for bullet mode
    if level == "bullet":
        # Split summary into sentences and format as bullet points
        import re
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) >= 2:
            summary = "\n• " + "\n• ".join(sentences)
    
    return summary


# --- Main CLI ---
def main():
    parser = argparse.ArgumentParser(description="Scrape, translate, and summarize a German news article.")
    parser.add_argument("url", help="Article URL to scrape and summarize")
    parser.add_argument("level", nargs="?", default="detailed",
                        choices=["short", "detailed", "bullet", "translate"],
                        help="Summary detail level, or 'translate' for the full English translation (default: detailed)")
    args = parser.parse_args()
    
    print(f"Article summarization started...", file=sys.stderr)
    
    # Step 1: Scrape
    print(f"  Step 1/3: Scraping article...", file=sys.stderr)
    raw_text = scrape_article(args.url)
    if not raw_text:
        print("ERROR: Could not scrape article from URL. The site may be blocking requests or the link may be broken.")
        sys.exit(1)
    print(f"  Scraped {len(raw_text)} characters of German text.", file=sys.stderr)
    
    # Step 2: Translate
    print(f"  Step 2/3: Translating German→English...", file=sys.stderr)
    setup_translator()
    en_text = translate(raw_text)
    if not en_text or en_text == raw_text:
        print("WARNING: Translation may have failed. Proceeding with original text.", file=sys.stderr)
        en_text = raw_text
    print(f"  Translated to {len(en_text)} characters of English.", file=sys.stderr)
    
    # Step 3: Summarize or output full translation
    if args.level == "translate":
        # Save full English translation to a text file
        import tempfile, datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"translation_{ts}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(en_text)
        print(f"\n{'─'*60}", file=sys.stderr)
        print(f"  Full translation saved to: {out_path}", file=sys.stderr)
        print(f"  Size: {len(en_text)} characters", file=sys.stderr)
        print(f"{'─'*60}", file=sys.stderr)
        # Print the file path on stdout so the agent can pick it up
        print(out_path)
    else:
        print(f"  Step 3/3: Summarizing with BART ({args.level})...", file=sys.stderr)
        summary = summarize(en_text, args.level)
        
        # Output
        print(f"\n{'─'*60}")
        print(summary)
        print(f"{'─'*60}")

if __name__ == "__main__":
    main()
