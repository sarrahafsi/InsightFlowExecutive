"""
Page web locale pour tester le pipeline OCR + Vision + fusion LLM en cliquant
sur "Choisir un fichier" — pas besoin de taper de commandes.

Usage :
    python test_image_pipeline_web.py

Puis ouvre http://localhost:8010 dans ton navigateur.
"""
import base64
import html
import json
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse

from intelligence.nlp.image_processor import process_image_async

app = FastAPI()

UPLOAD_DIR = Path(__file__).parent / "uploads" / "test_pipeline"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PAGE_HEAD = """<!doctype html><html><head><meta charset="utf-8">
<title>Test pipeline image — InsightFlow</title>
<style>
body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #222; }
h1 { font-size: 20px; }
form { margin: 24px 0; padding: 20px; border: 2px dashed #ccc; border-radius: 8px; text-align: center; }
button { padding: 8px 20px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
button:hover { background: #1d4ed8; }
.block { margin: 18px 0; padding: 14px 16px; background: #f8f9fa; border-radius: 8px; border: 1px solid #eee; }
.block h3 { margin: 0 0 8px; font-size: 13px; text-transform: uppercase; color: #666; letter-spacing: 0.3px; }
pre { white-space: pre-wrap; word-wrap: break-word; font-size: 13px; margin: 0; }
img { max-width: 100%; border-radius: 8px; margin: 12px 0; border: 1px solid #ddd; }
</style></head><body>
<h1>Test pipeline OCR + Vision + fusion LLM</h1>
<form action="/upload" method="post" enctype="multipart/form-data">
  <input type="file" name="file" accept="image/*" required>
  <br><br>
  <button type="submit">Analyser l'image</button>
</form>
"""

PAGE_TAIL = "</body></html>"


@app.get("/", response_class=HTMLResponse)
def home():
    return PAGE_HEAD + PAGE_TAIL


@app.post("/upload", response_class=HTMLResponse)
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    saved_path = UPLOAD_DIR / file.filename
    saved_path.write_bytes(content)

    result = await process_image_async(saved_path)

    img_b64 = base64.b64encode(content).decode()
    img_src = f"data:{file.content_type};base64,{img_b64}"

    structured_json = json.dumps(result["structured"], indent=2, ensure_ascii=False)

    ocr_safe = html.escape(result["ocr_text"] or "(aucun texte detecte)")
    vision_safe = html.escape(result["vision_caption"] or "(pas de caption)")
    json_safe = html.escape(structured_json)
    content_safe = html.escape(result["content"])

    body = f"""
    <img src="{img_src}" alt="uploaded image">
    <div class="block"><h3>Texte OCR detecte</h3><pre>{ocr_safe}</pre></div>
    <div class="block"><h3>Caption Vision (BLIP)</h3><pre>{vision_safe}</pre></div>
    <div class="block"><h3>Resultat structure (JSON)</h3><pre>{json_safe}</pre></div>
    <div class="block"><h3>Texte final pour le pipeline NLP</h3><pre>{content_safe}</pre></div>
    <p><a href="/">&larr; Analyser une autre image</a></p>
    """
    return PAGE_HEAD + body + PAGE_TAIL


if __name__ == "__main__":
    import uvicorn
    print("Ouvre http://localhost:8010 dans ton navigateur")
    uvicorn.run(app, host="0.0.0.0", port=8010)
