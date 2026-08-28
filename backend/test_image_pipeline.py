"""
Test manuel du pipeline OCR + Vision + fusion LLM sur une image de ton choix.

Usage :
    python test_image_pipeline.py chemin/vers/ton_image.png
"""
import json
import sys

from intelligence.nlp.image_processor import process_image

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage : python test_image_pipeline.py chemin/vers/image.png")
        sys.exit(1)

    image_path = sys.argv[1]
    print(f"Traitement de : {image_path}\n")

    result = process_image(image_path)

    print("-- Texte OCR detecte --------------------------")
    print(result["ocr_text"] or "(aucun texte detecte)")

    print("\n-- Caption Vision (BLIP) -----------------------")
    print(result["vision_caption"] or "(pas de caption)")

    print("\n-- Resultat structure (JSON) --------------------")
    print(json.dumps(result["structured"], indent=2, ensure_ascii=True))

    print("\n-- Texte final pour le pipeline NLP -------------")
    print(result["content"])
