#!/bin/bash
# =========================================================
# InsightForge AI - macOS Startup Script
# Creates a virtual environment (if needed), installs
# dependencies, checks configuration, and launches the app.
# (Was made by Oleh Datsyk)
# =========================================================

cd "$(dirname "$0")"

# If something fails before the server starts, keep the window open long
# enough to read the error instead of Terminal closing it immediately.
on_exit() {
    status=$?
    if [ $status -ne 0 ]; then
        echo ""
        echo "[ERROR] InsightForge AI stopped with an error (see messages above)."
        read -p "Press Enter to close this window..."
    fi
}
trap on_exit EXIT

echo ""
echo "==========================================================="
echo "  InsightForge AI - Starting Up (Was made by Oleh Datsyk)"
echo "==========================================================="
echo ""

# --- Sanity check: make sure the ZIP was actually extracted ---
if [ ! -f "app.py" ]; then
    echo "[ERROR] app.py was not found in this folder."
    echo "Make sure you fully extracted the ZIP file first, then run this"
    echo "script from inside the extracted folder (not from inside the .zip)."
    exit 1
fi

# --- Check Python is installed ---
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 was not found."
    echo "Install Python 3.11+ from https://www.python.org/downloads/ or via Homebrew: brew install python"
    exit 1
fi

set -e

# --- Create virtual environment if missing ---
if [ ! -d "venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv venv
else
    echo "[1/4] Virtual environment already exists."
fi

# --- Activate virtual environment ---
source venv/bin/activate

# --- Install dependencies ---
echo "[2/4] Installing dependencies..."
pip install --upgrade pip > /dev/null
pip install -r requirements.txt

# --- Check .env file exists ---
echo "[3/4] Checking configuration..."
if [ ! -f ".env" ]; then
    echo "[WARN] No .env file found. Copying .env.example to .env"
    cp .env.example .env
    echo "Please edit .env and add at least one AI provider API key"
    echo "(OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY) before"
    echo "using the research features."
fi

# --- Launch application ---
echo "[4/4] Launching InsightForge AI at http://localhost:8000"
echo "Press CTRL+C to stop the server."
echo ""
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
