"""Prove summarize.translate() falls back to the offline ONNX engine.

Simulates total online failure (all three free endpoints down) and checks that
the offline tier produces English instead of leaving German text in place.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# run from anywhere: make the repo root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import summarize

DE = ("Die Polizei ermittelt nach einem Brand in einem Mehrfamilienhaus in Olching. "
      "Der Landkreis Fürstenfeldbruck baut die Radwege zwischen Germering und Puchheim aus.")

print("--- online tier: forced DOWN ---")
summarize._online_translate = lambda text: None

out = summarize.translate(DE)
print("RESULT:", out)

low = out.lower()
english = any(w in low for w in ("the ", "police", "fire", "district", "investigating"))
print("LOOKS_ENGLISH:", english)
print("VERDICT:", "PASS - offline fallback engaged" if english else "FAIL - still German/empty")
