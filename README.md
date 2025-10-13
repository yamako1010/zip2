# MonoZip Web - Local Setup

Follow the steps below to run the MonoZip Web application locally and access it at http://127.0.0.1:5000.

## Prerequisites
- Python 3.12 installed and available as `python3.12`.
- pip is up to date (`python3.12 -m pip install --upgrade pip`).

## Quick Start
1. `cd ~/Documents/Codex/ZIP2`
2. `python3.12 -m venv .venv`
3. `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
4. `pip install -r requirements.txt`
5. `python app.py`
6. Open http://127.0.0.1:5000 in your browser.

Press `Ctrl+C` in the terminal to stop the server.

## Helper Scripts
- macOS/Linux: `./start_mac.sh`
- Windows: `start_win.bat`

Each script:
1. Verifies that `python3.12` is installed.
2. Creates the `.venv` virtual environment if it does not exist.
3. Installs the dependencies from `requirements.txt`.
4. Launches `app.py`.

If `python3.12` is missing, install it first and rerun the script.
