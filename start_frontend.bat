@echo off
cd /D "%~dp0frontend"
echo Starting frontend on port 3000...
node node_modules/next/dist/bin/next start --port 3000
