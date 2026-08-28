"""
Test manuel de la transcription speech-to-text (faster-whisper) sur un fichier
audio de ton choix.

Usage :
    python test_speech_pipeline.py chemin/vers/ton_audio.mp3
"""
import sys

from intelligence.nlp.transcription import transcribe_audio

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage : python test_speech_pipeline.py chemin/vers/audio.mp3")
        sys.exit(1)

    audio_path = sys.argv[1]
    print(f"Traitement de : {audio_path}\n")

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    text = transcribe_audio(audio_bytes)

    print("-- Texte transcrit ------------------------------")
    print(text or "(aucun texte transcrit / echec)")
