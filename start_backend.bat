@echo off
cd /D "%~dp0backend"
echo Starting backend on port 8000...
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
