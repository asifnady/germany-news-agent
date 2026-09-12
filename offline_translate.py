"""Offline DE->EN translation via ONNX Runtime — last-resort fallback.

Why this exists: the free online endpoints (Google gtx -> dict-chrome-ex ->
MyMemory) rate-limit (HTTP 429) under load. This module gives summarize.py a
local engine to fall back on, using the same Marian/Opus-MT model family that
Argos used, but executed by ONNX Runtime instead of CTranslate2/PyTorch.

That matters on Windows hosts with Smart App Control in Enforcement mode: SAC
blocks the unsigned native DLLs behind ctranslate2 / torch / sentencepiece,
but onnxruntime and tokenizers are signed and load fine.

Optional dependencies (NOT required for the main pipeline):
    pip install numpy onnxruntime tokenizers

Model files (~106 MB, not in git) — fetch with:
    python tools/fetch_offline_model.py

Public API:
    available() -> bool          cheap check for model files + imports
    translate(text) -> str       returns English text, or raises on failure
"""
import json
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "models", "opus-mt-de-en")

ENCODER = "onnx_encoder_model_quantized.onnx"
DECODER = "onnx_decoder_model_quantized.onnx"

_state = {"loaded": False, "ok": False, "why": "not loaded",
          "enc": None, "dec": None, "tok": None, "start": 58100, "eos": 0}


def _log(msg):
    print(f"  [offline] {msg}", file=sys.stderr)


def _register_msvc_dlls():
    """This class of host may lack the system VC++ runtime; the venv bundles it."""
    for base in (sys.prefix, getattr(sys, "base_prefix", sys.prefix)):
        d = os.path.join(base, "Lib", "site-packages", "_runtime_dlls")
        if os.name == "nt" and os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass


def model_present():
    return all(os.path.exists(os.path.join(MODEL_DIR, f))
               for f in ("tokenizer.json", "config.json", ENCODER, DECODER))


def available():
    """True when the model files exist and the optional deps import."""
    if not model_present():
        return False
    return _load()[0]


def _load():
    if _state["loaded"]:
        return _state["ok"], _state["why"]
    _state["loaded"] = True

    if not model_present():
        _state["why"] = f"model files missing in {MODEL_DIR}"
        return False, _state["why"]

    try:
        _register_msvc_dlls()
        import numpy as np  # noqa: F401
        import onnxruntime as ort
        from tokenizers import Tokenizer
    except Exception as e:
        _state["why"] = f"optional deps unavailable ({e})"
        return False, _state["why"]

    try:
        tj = json.load(open(os.path.join(MODEL_DIR, "tokenizer.json"), encoding="utf-8"))
        # The public Transformers.js exports ship precompiled_charsmap: null,
        # which the Rust tokenizer rejects outright. Drop the normalizer and
        # approximate it with NFKC in norm() below.
        if isinstance(tj.get("normalizer"), dict) and tj["normalizer"].get("precompiled_charsmap") is None:
            tj["normalizer"] = None
        tok = Tokenizer.from_str(json.dumps(tj))
        tok.enable_truncation(max_length=512)

        cfg = json.load(open(os.path.join(MODEL_DIR, "config.json"), encoding="utf-8"))
        _state["start"] = cfg.get("decoder_start_token_id") or cfg.get("pad_token_id") or 58100
        _state["eos"] = cfg.get("eos_token_id") or 0

        _state["enc"] = ort.InferenceSession(os.path.join(MODEL_DIR, ENCODER),
                                             providers=["CPUExecutionProvider"])
        _state["dec"] = ort.InferenceSession(os.path.join(MODEL_DIR, DECODER),
                                             providers=["CPUExecutionProvider"])
        _state["tok"] = tok
    except Exception as e:
        _state["why"] = f"model load failed ({e})"
        return False, _state["why"]

    _state["ok"] = True
    _state["why"] = "ready"
    return True, "ready"


def _norm(text):
    """Stand-in for the sentencepiece charsmap the public exports blank out."""
    t = text.replace("\u00a0", " ").replace("\u201e", '"').replace("\u201c", '"')
    return unicodedata.normalize("NFKC", t)


def translate(text, max_new=200):
    """Translate German -> English offline. Raises RuntimeError if unavailable."""
    ok, why = _load()
    if not ok:
        raise RuntimeError(f"offline translator unavailable: {why}")

    import numpy as np

    tok = _state["tok"]
    enc = _state["enc"]
    dec = _state["dec"]
    start = _state["start"]
    eos = _state["eos"]

    encoded = tok.encode(_norm(text))
    ids = np.array([encoded.ids], dtype=np.int64)
    mask = np.array([encoded.attention_mask], dtype=np.int64)
    hidden = enc.run(None, {"input_ids": ids, "attention_mask": mask})[0]

    # Greedy decoding. Measured on an i3-8100: ~0.6-2.3 s per sentence.
    # Beam search was tried and rejected — it gave identical output on simple
    # sentences and only marginal gains on hard ones, at ~56 s per sentence
    # (the non-merged decoder recomputes the whole prefix each step).
    cur = [start]
    for _ in range(max_new):
        logits = dec.run(None, {
            "input_ids": np.array([cur], dtype=np.int64),
            "encoder_attention_mask": mask,
            "encoder_hidden_states": hidden,
        })[0][0, -1]
        nxt = int(np.argmax(logits))
        if nxt == eos:
            break
        cur.append(nxt)

    return tok.decode(cur[1:], skip_special_tokens=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src = " ".join(sys.argv[1:]) or "Die Polizei ermittelt nach einem Brand in Olching."
    print(translate(src))
