"""Download the offline DE->EN model used by offline_translate.py.

    python tools/fetch_offline_model.py

Fetches ~106 MB (quantised Marian/Opus-MT DE->EN exported to ONNX) into
models/opus-mt-de-en/. Files are NOT in git — this script is the reproducible
way to get them. Safe to re-run: existing complete files are skipped.

Model: Xenova/opus-mt-de-en (Transformers.js export of Helsinki-NLP/opus-mt-de-en)
"""
import os
import sys
import urllib.request

BASE = "https://huggingface.co/Xenova/opus-mt-de-en/resolve/main/"
HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(os.path.dirname(HERE), "models", "opus-mt-de-en")

FILES = [
    ("tokenizer.json", "tokenizer.json"),
    ("config.json", "config.json"),
    ("onnx/encoder_model_quantized.onnx", "onnx_encoder_model_quantized.onnx"),
    ("onnx/decoder_model_quantized.onnx", "onnx_decoder_model_quantized.onnx"),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(DEST, exist_ok=True)
    for remote, local in FILES:
        out = os.path.join(DEST, local)
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            print(f"  skip {local} ({os.path.getsize(out):,} bytes)")
            continue
        print(f"  downloading {remote} ...", flush=True)
        req = urllib.request.Request(BASE + remote, headers={"User-Agent": "Mozilla/5.0"})
        tmp = out + ".part"
        with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
            f.write(r.read())
        os.replace(tmp, out)
        print(f"    -> {local} ({os.path.getsize(out):,} bytes)")
    print(f"DONE — model in {DEST}")
    print("Now install the optional deps:  pip install numpy onnxruntime tokenizers")


if __name__ == "__main__":
    main()
