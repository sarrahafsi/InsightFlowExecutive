"""
Test du pipeline emotion 3 niveaux
Usage : python backend/test_emotion_pipeline.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nlp.emotion import _classify, _load_temperature, CONFIDENCE_THRESHOLD

T = _load_temperature()
print(f"Temperature T = {T}")
print(f"Seuil confiance = {CONFIDENCE_THRESHOLD}")
print("=" * 55)

tests = [
    # (texte, sentiment, resultat_attendu)
    ("The API deployment failed and the team is blocked",       "NEGATIVE", "frustration"),
    ("Great news, the feature is live and working perfectly",   "POSITIVE", "satisfaction"),
    ("Meeting tomorrow at 9am to review the sprint",            "NEUTRAL",  "neutral"),
    ("We are running out of time, deadline is tomorrow",        "NEGATIVE", "urgency"),
    ("I am worried about the security issue in production",     "NEGATIVE", "concern"),
    ("Probleme avec le developpement API",                      "NEGATIVE", "frustration"),
    ("Le deploiement marche finalement",                        "POSITIVE", "satisfaction"),
]

correct = 0
for text, sentiment, expected in tests:
    result = _classify(text, sentiment_label=sentiment)
    label  = result["label"] if result else "N/A"
    score  = result["score"] if result else 0.0
    ok     = label == expected
    correct += int(ok)

    level = "L1+L2" if score >= CONFIDENCE_THRESHOLD else "L1+L2+L3(Ollama)"
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {level}")
    print(f"      Texte    : {text[:50]}")
    print(f"      Attendu  : {expected}")
    print(f"      Obtenu   : {label} (score calibre={score:.2f})")
    print()

print("=" * 55)
print(f"Resultat : {correct}/{len(tests)} correct ({correct/len(tests)*100:.0f}%)")
