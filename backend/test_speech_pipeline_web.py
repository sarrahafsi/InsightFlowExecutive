"""
Page web locale pour tester la transcription speech-to-text (faster-whisper)
en cliquant sur "Choisir un fichier" — pas besoin de taper de commandes.

Usage :
    python test_speech_pipeline_web.py

Puis ouvre http://localhost:8011 dans ton navigateur.
"""
import asyncio
import html
import time
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse

from intelligence.nlp.transcription import transcribe_audio

app = FastAPI()

UPLOAD_DIR = Path(__file__).parent / "uploads" / "test_speech"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PAGE_HEAD = """<!doctype html><html><head><meta charset="utf-8">
<title>Test speech-to-text — InsightFlow</title>
<style>
body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #222; }
h1 { font-size: 20px; }
form { margin: 24px 0; padding: 20px; border: 2px dashed #ccc; border-radius: 8px; text-align: center; }
button { padding: 8px 20px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
button:hover { background: #1d4ed8; }
.block { margin: 18px 0; padding: 14px 16px; background: #f8f9fa; border-radius: 8px; border: 1px solid #eee; }
.block h3 { margin: 0 0 8px; font-size: 13px; text-transform: uppercase; color: #666; letter-spacing: 0.3px; }
pre { white-space: pre-wrap; word-wrap: break-word; font-size: 13px; margin: 0; }
audio { width: 100%; margin: 12px 0; }
.hint { font-size: 12.5px; color: #888; margin-top: 8px; }
</style></head><body>
<h1>Test transcription audio (faster-whisper)</h1>
<form action="/upload" method="post" enctype="multipart/form-data">
  <input type="file" name="file" accept="audio/*" required>
  <br><br>
  <button type="submit">Transcrire l'audio</button>
  <p class="hint">Formats acceptes : mp3, wav, m4a, ogg... (n'importe quel format audio courant)</p>
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

    t0 = time.time()
    text = await asyncio.to_thread(transcribe_audio, content)
    elapsed = round(time.time() - t0, 2)

    text_safe = html.escape(text or "(aucun texte transcrit / echec)")

    body = f"""
    <audio controls src="/audio/{file.filename}"></audio>
    <div class="block"><h3>Texte transcrit ({elapsed}s)</h3><pre>{text_safe}</pre></div>
    <p><a href="/">&larr; Transcrire un autre fichier</a></p>
    """
    return PAGE_HEAD + body + PAGE_TAIL


@app.get("/audio/{filename}")
def get_audio(filename: str):
    from fastapi.responses import FileResponse
    path = UPLOAD_DIR / filename
    return FileResponse(path)


if __name__ == "__main__":
    import uvicorn
    print("Ouvre http://localhost:8011 dans ton navigateur")
    uvicorn.run(app, host="0.0.0.0", port=8011)
