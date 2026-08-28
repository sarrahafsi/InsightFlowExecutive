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
.record-box { margin: 24px 0; padding: 24px; border: 2px solid #2563eb; border-radius: 8px; text-align: center; }
form { margin: 24px 0; padding: 20px; border: 2px dashed #ccc; border-radius: 8px; text-align: center; }
button { padding: 8px 20px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
button:hover { background: #1d4ed8; }
button:disabled { background: #aab; cursor: not-allowed; }
button.recording { background: #dc2626; }
button.recording:hover { background: #b91c1c; }
.block { margin: 18px 0; padding: 14px 16px; background: #f8f9fa; border-radius: 8px; border: 1px solid #eee; }
.block h3 { margin: 0 0 8px; font-size: 13px; text-transform: uppercase; color: #666; letter-spacing: 0.3px; }
pre { white-space: pre-wrap; word-wrap: break-word; font-size: 13px; margin: 0; }
audio { width: 100%; margin: 12px 0; }
.hint { font-size: 12.5px; color: #888; margin-top: 8px; }
.status { font-size: 14px; margin: 10px 0; color: #333; min-height: 20px; }
.or-sep { text-align: center; color: #999; font-size: 12.5px; margin: 8px 0; }
</style></head><body>
<h1>Test transcription audio (faster-whisper)</h1>

<div class="record-box">
  <button id="recordBtn" type="button">Enregistrer depuis le micro</button>
  <div class="status" id="status"></div>
  <audio id="preview" controls style="display:none"></audio>
  <br>
  <button id="sendBtn" type="button" disabled>Transcrire cet enregistrement</button>
</div>

<div class="or-sep">— ou —</div>

<form action="/upload" method="post" enctype="multipart/form-data">
  <input type="file" name="file" accept="audio/*" required>
  <br><br>
  <button type="submit">Transcrire un fichier existant</button>
  <p class="hint">Formats acceptes : mp3, wav, m4a, ogg... (n'importe quel format audio courant)</p>
</form>

<script>
let mediaRecorder, chunks = [], recordedBlob = null;
const recordBtn = document.getElementById('recordBtn');
const sendBtn = document.getElementById('sendBtn');
const status = document.getElementById('status');
const preview = document.getElementById('preview');

recordBtn.addEventListener('click', async () => {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = () => {
      recordedBlob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      preview.src = URL.createObjectURL(recordedBlob);
      preview.style.display = 'block';
      sendBtn.disabled = false;
      recordBtn.textContent = 'Enregistrer depuis le micro';
      recordBtn.classList.remove('recording');
      status.textContent = 'Enregistrement termine — ecoute-le puis clique sur "Transcrire".';
      stream.getTracks().forEach(t => t.stop());
    };
    mediaRecorder.start();
    recordBtn.textContent = 'Arreter l\\'enregistrement';
    recordBtn.classList.add('recording');
    status.textContent = 'Enregistrement en cours...';
    sendBtn.disabled = true;
  } catch (err) {
    status.textContent = 'Micro inaccessible : ' + err.message + ' (autorise le microphone pour ce site)';
  }
});

sendBtn.addEventListener('click', async () => {
  if (!recordedBlob) return;
  sendBtn.disabled = true;
  status.textContent = 'Transcription en cours...';
  const ext = (mediaRecorder.mimeType || 'audio/webm').includes('ogg') ? 'ogg' : 'webm';
  const formData = new FormData();
  formData.append('file', recordedBlob, 'recording.' + ext);
  const resp = await fetch('/upload', { method: 'POST', body: formData });
  const htmlText = await resp.text();
  document.open();
  document.write(htmlText);
  document.close();
});
</script>
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
