"""
Benchmark OCR — InsightFlow Executive PFE
Moteurs   : EasyOCR, Tesseract (pytesseract), PaddleOCR
Images    : texte synthétique généré via PIL (Pillow), vérité terrain exacte connue
Métriques : word accuracy, character error rate (CER), load_sec, inference_sec

Complète benchmark_captioning.py (Vision) pour la Phase 0 du benchmark
multimodal — même esprit : comparer plusieurs candidats sur un jeu de test
avec vérité terrain connue, produire un tableau reproductible pour le
rapport PFE.

Dépendances supplémentaires (installées seulement pour ce benchmark) :
    pip install easyocr pytesseract paddleocr paddlepaddle
Tesseract nécessite aussi le binaire système (déjà présent sur cette machine :
C:\\Users\\lenovo\\AppData\\Local\\Programs\\Tesseract-OCR\\tesseract.exe) —
sur une autre machine il faudrait l'installer séparément (voir section
"Résultats" du benchmark pour ce que ça implique comme argument de choix).
"""

import csv
import textwrap
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMAGES_DIR   = Path(__file__).parent / "benchmark_ocr_images"
RESULTS_FILE = Path(__file__).parent / "benchmark_ocr_results.csv"

TESSERACT_DEFAULT_PATH = r"C:\Users\lenovo\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# ── Échantillons de texte (vérité terrain exacte) — mirrorent les catégories
# cibles du besoin multimodal : erreur technique, dashboard, ticket, chat ──
SAMPLES = {
    "ocr_error_msg":     "Deployment failed. Database connection timeout. Critical error code 503.",
    "ocr_dashboard_kpi": "Monthly Revenue 145K EUR Target 150K EUR Status On Track",
    "ocr_ticket_field":  "SCRUM-231 API rate limiting fails under load Status In Progress Priority High",
    "ocr_chat_message":  "Sarah Hafsi Sprint review moved to 3pm everyone ok Karim Haddad Works for me",
    "ocr_paragraph":     "The application has encountered an unexpected error and needs to close. Please contact support if this issue persists.",
    "ocr_small_caps":    "URGENT ACTION REQUIRED BEFORE FRIDAY DEADLINE APPROVE BUDGET NOW",
    "ocr_stack_trace":   "Traceback most recent call last File sync_worker.py line 42 in run ConnectionTimeoutError could not connect to database",
    "ocr_mixed_case":    "Invoice INV-2024-0091 Total Due 4250.00 EUR Payment Status Overdue",
}


# ── Génération des images de test ────────────────────────────────────────────
def generate_test_images() -> dict:
    IMAGES_DIR.mkdir(exist_ok=True)
    images = {}
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()

    for name, text in SAMPLES.items():
        wrapped = textwrap.fill(text, width=48)
        lines = wrapped.split("\n")
        w, h = 760, 50 + 34 * len(lines)
        img = Image.new("RGB", (w, h), color="white")
        draw = ImageDraw.Draw(img)
        y = 18
        for line in lines:
            draw.text((20, y), line, fill="black", font=font)
            y += 34
        path = IMAGES_DIR / f"{name}.png"
        img.save(path)
        images[name] = path

    print(f"[OK] {len(images)} images generees dans : {IMAGES_DIR}")
    return images


# ── Métriques ────────────────────────────────────────────────────────────────
def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def word_accuracy(hyp: str, ref: str) -> float:
    """Fraction des mots de reference retrouves dans le texte extrait (ordre non contraignant —
    l'OCR peut reordonner des lignes, ce qui ne doit pas etre penalise comme une erreur)."""
    hyp_words = _normalize(hyp).split()
    ref_words = _normalize(ref).split()
    if not ref_words:
        return 0.0
    hyp_set = hyp_words[:]
    correct = 0
    for w in ref_words:
        if w in hyp_set:
            correct += 1
            hyp_set.remove(w)
    return round(correct / len(ref_words), 4)


def _levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            tmp = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = tmp
    return dp[n]


def cer(hyp: str, ref: str) -> float:
    """Character Error Rate — distance d'edition / longueur de la reference (0 = parfait)."""
    ref_n = _normalize(ref)
    hyp_n = _normalize(hyp)
    if not ref_n:
        return 1.0
    return round(_levenshtein(hyp_n, ref_n) / len(ref_n), 4)


# ── Loaders / Inférences par moteur ──────────────────────────────────────────
def load_easyocr():
    import easyocr
    return easyocr.Reader(["en"], gpu=False, verbose=False)


def infer_easyocr(reader, path: Path) -> str:
    result = reader.readtext(str(path), detail=0)
    return " ".join(result)


def load_tesseract():
    import os
    import pytesseract
    if os.path.exists(TESSERACT_DEFAULT_PATH):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_DEFAULT_PATH
    return pytesseract


def infer_tesseract(engine, path: Path) -> str:
    return engine.image_to_string(Image.open(path))


def load_paddleocr():
    """
    L'API PaddleOCR a change entre versions : use_angle_cls/show_log (<3.x)
    vs use_textline_orientation (>=3.x, notre version installee: 3.7.0).
    On tente la nouvelle API d'abord, avec repli sur l'ancienne.
    """
    from paddleocr import PaddleOCR
    try:
        return PaddleOCR(use_textline_orientation=True, lang="en")
    except TypeError:
        return PaddleOCR(use_angle_cls=True, lang="en", show_log=False)


def infer_paddleocr(engine, path: Path) -> str:
    result = engine.ocr(str(path))
    lines = []
    for block in result or []:
        # API >=3.x : dict avec 'rec_texts' ; API <3.x : liste de [box, (text, score)]
        if isinstance(block, dict) and "rec_texts" in block:
            lines.extend(block["rec_texts"])
        else:
            for line in block or []:
                lines.append(line[1][0])
    return " ".join(lines)


ENGINES = {
    "EasyOCR":   {"loader": load_easyocr,   "infer": infer_easyocr,   "approx_size_mb": 65},
    "Tesseract": {"loader": load_tesseract, "infer": infer_tesseract, "approx_size_mb": 15},
    "PaddleOCR": {"loader": load_paddleocr, "infer": infer_paddleocr, "approx_size_mb": 45},
}


# ── Benchmark principal ───────────────────────────────────────────────────────
def run_benchmark(images: dict) -> list:
    results = []
    n = len(images)

    for engine_name, meta in ENGINES.items():
        print(f"\n{'=' * 65}")
        print(f"  {engine_name}  (~{meta['approx_size_mb']} MB)")
        print(f"{'=' * 65}")

        print("  Chargement...", end=" ", flush=True)
        try:
            t0 = time.time()
            loaded = meta["loader"]()
            load_sec = round(time.time() - t0, 2)
            print(f"{load_sec}s")
        except Exception as e:
            print(f"ERREUR : {e}")
            for img_name in images:
                results.append(_err(engine_name, img_name, meta, str(e)))
            continue

        for idx, (img_name, img_path) in enumerate(images.items(), 1):
            print(f"  [{idx:02d}/{n}] {img_name:<20}", end=" ", flush=True)
            try:
                t0 = time.time()
                extracted = meta["infer"](loaded, img_path)
                inf_sec = round(time.time() - t0, 2)

                ref = SAMPLES[img_name]
                wa  = word_accuracy(extracted, ref)
                ce  = cer(extracted, ref)

                print(f"inf={inf_sec}s  word_acc={wa:.3f}  CER={ce:.3f}")

                results.append({
                    "engine": engine_name, "image": img_name,
                    "extracted_text": extracted, "reference": ref,
                    "load_sec": load_sec, "inference_sec": inf_sec,
                    "word_accuracy": wa, "cer": ce,
                    "approx_size_mb": meta["approx_size_mb"], "error": "",
                })
            except Exception as e:
                print(f"ERREUR : {e}")
                results.append(_err(engine_name, img_name, meta, str(e), load_sec))

        del loaded

    return results


def _err(engine_name, img_name, meta, error, load_sec=-1):
    return {
        "engine": engine_name, "image": img_name,
        "extracted_text": "", "reference": SAMPLES.get(img_name, ""),
        "load_sec": load_sec, "inference_sec": -1,
        "word_accuracy": -1, "cer": -1,
        "approx_size_mb": meta["approx_size_mb"], "error": error,
    }


def save_results(results: list):
    fields = [
        "engine", "image", "extracted_text", "reference",
        "load_sec", "inference_sec", "word_accuracy", "cer",
        "approx_size_mb", "error",
    ]
    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(results)
    print(f"\n[OK] CSV sauvegarde : {RESULTS_FILE}")


def print_summary(results: list):
    from collections import defaultdict
    metrics = defaultdict(lambda: defaultdict(list))
    for r in results:
        if r["inference_sec"] >= 0:
            e = r["engine"]
            metrics[e]["inf"].append(r["inference_sec"])
            metrics[e]["load"].append(r["load_sec"])
            if r["word_accuracy"] >= 0: metrics[e]["wa"].append(r["word_accuracy"])
            if r["cer"] >= 0:           metrics[e]["cer"].append(r["cer"])

    def avg(lst): return round(sum(lst) / len(lst), 3) if lst else -1

    print(f"\n{'=' * 75}")
    print(f"  {'Moteur':<12} {'Load':>7} {'Inf moy':>9} {'WordAcc':>9} {'CER':>7} {'MB':>6}")
    print(f"{'=' * 75}")
    for engine in ENGINES:
        m = metrics[engine]
        print(f"  {engine:<12}"
              f"  {m['load'][0] if m['load'] else -1:>6}s"
              f"  {avg(m['inf']):>8}s"
              f"  {avg(m['wa']):>9}"
              f"  {avg(m['cer']):>7}"
              f"  {ENGINES[engine]['approx_size_mb']:>5}MB")
    print(f"{'=' * 75}")
    print("""
  Legende :
  • WordAcc = fraction des mots de reference retrouves dans le texte extrait (0->1, plus = mieux)
  • CER     = character error rate, distance d'edition / longueur reference (0->1, moins = mieux)
    """)
    print(f"[i] Resultats complets -> {RESULTS_FILE}")


if __name__ == "__main__":
    print("Etape 1/3 — Generation des images de texte de test...")
    images = generate_test_images()

    print("\nEtape 2/3 — Benchmark (telechargement modeles au 1er lancement)...")
    results = run_benchmark(images)

    print("\nEtape 3/3 — Sauvegarde...")
    save_results(results)
    print_summary(results)
