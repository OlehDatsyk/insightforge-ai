# INSTRUCTION.md - Complete Beginner's Guide

This guide assumes **no prior experience**. Follow the steps in order. Every command is
explained - you don't need to know what it does beforehand.

> **Operating system note:** Windows steps use `Start App.bat`. macOS/Linux steps use
> `Start App (Mac).command`. Terminal commands are given for both where they differ.

---

## 1. Install Python

InsightForge AI needs **Python 3.11 or newer**.

- **Windows:** Go to https://www.python.org/downloads/ and download the latest Python 3
  installer. Run it. **Check the box that says "Add python.exe to PATH"** before clicking
  Install - this step is easy to miss and causes problems later if skipped.
- **macOS:** Open Terminal (Cmd+Space, type "Terminal", Enter) and run:
  ```bash
  brew install python
  ```
  If you don't have Homebrew, install it first from https://brew.sh, or download Python
  directly from https://www.python.org/downloads/.
- **Verify it worked** by opening a terminal/command prompt and running:
  ```bash
  python --version
  ```
  (On macOS/Linux you may need `python3 --version` instead.) You should see something like
  `Python 3.11.9` or newer.

## 2. Install Git

Git lets you download ("clone") the project and later push it to GitHub.

- **Windows:** Download from https://git-scm.com/download/win and run the installer,
  accepting the defaults.
- **macOS:** Run `git --version` in Terminal - macOS will offer to install the Xcode Command
  Line Tools, which includes Git. Accept.
- **Verify:** `git --version` should print a version number.

## 3. Install Visual Studio Code

Download from https://code.visualstudio.com and install it (accept the defaults). This is
the editor you'll use to open and edit the project.

Recommended extensions (open VS Code -> Extensions icon on the left sidebar -> search and
install): **Python** (by Microsoft) and **Pylance**.

## 4. Download the project

If you received this project as a ZIP file: unzip it anywhere convenient, e.g.
`Documents/insightforge-ai`.

If you're cloning from GitHub instead:
```bash
git clone https://github.com/<your-username>/insightforge-ai.git
cd insightforge-ai
```

## 5. Open the project in VS Code

- Open VS Code.
- **File -> Open Folder...** and select the `insightforge-ai` folder.
- Open the built-in terminal: **Terminal -> New Terminal**. All commands below are typed here.

## 6. Create the virtual environment

A virtual environment keeps this project's Python packages separate from everything else on
your computer.

```bash
python -m venv venv
```
(macOS/Linux: use `python3` if `python` isn't recognized.)

This creates a `venv` folder inside the project. You'll see it appear in the VS Code file
explorer.

## 7. Activate the virtual environment

- **Windows (Command Prompt or PowerShell):**
  ```bash
  venv\Scripts\activate
  ```
- **macOS/Linux:**
  ```bash
  source venv/bin/activate
  ```

You'll know it worked because your terminal prompt now starts with `(venv)`.

> You must activate the virtual environment every time you open a new terminal to work on
> this project. The `Start App` scripts do this for you automatically.

## 8. Install dependencies

With the virtual environment activated:
```bash
pip install -r requirements.txt
```
This downloads FastAPI, the OpenAI/Anthropic/Gemini SDKs, and everything else the project
needs. It may take a minute or two the first time.

## 9. Create `.env`

Copy the example environment file:
```bash
cp .env.example .env
```
(Windows Command Prompt: `copy .env.example .env`)

Open the new `.env` file in VS Code. This is where your API keys and settings live. It is
**never** uploaded to GitHub (see `.gitignore`).

## 10. Add your OpenAI API key

1. Go to https://platform.openai.com/api-keys and sign in (or create an account).
2. Click **Create new secret key**, copy it (you won't be able to see it again).
3. In `.env`, set:
   ```
   OPENAI_API_KEY=sk-...your-key-here...
   ```

## 11. Add your Anthropic API key

1. Go to https://console.anthropic.com/settings/keys and sign in.
2. Create a key, copy it.
3. In `.env`, set:
   ```
   ANTHROPIC_API_KEY=sk-ant-...your-key-here...
   ```

## 12. Add your Gemini API key

1. Go to https://aistudio.google.com/apikey and sign in with a Google account.
2. Click **Create API key**, copy it.
3. In `.env`, set:
   ```
   GEMINI_API_KEY=...your-key-here...
   ```

> **You only need one of these three to run the app.** Adding all three lets you see the
> automatic fallback system and multi-model routing in action, which is the most impressive
> part of this project to demonstrate.

## 13. Configure providers

Still in `.env`, review (and optionally change) these lines:
```
PRIMARY_AI_PROVIDER=openai
FALLBACK_AI_PROVIDER=anthropic
SECONDARY_FALLBACK_AI_PROVIDER=gemini

PLANNING_PROVIDER=openai
ANALYSIS_PROVIDER=anthropic
CROSSCHECK_PROVIDER=gemini
SYNTHESIS_PROVIDER=anthropic
```
If you only configured one provider's API key, it's fine to leave these as-is - the router
automatically skips unconfigured providers. You can also change these later from the
**Settings** page in the running app, without editing `.env` again.

## 14. Run the application

**Easiest way:** double-click `Start App.bat` (Windows) or run `Start App (Mac).command`
(macOS - see step 14a below if it won't open). These scripts do everything automatically:
check Python, create the virtual environment if needed (and rebuild it automatically if it
was copied from another computer), install dependencies, check for `.env`, and start the
server.

On Windows, the server runs in its own window titled **"InsightForge AI Server"** so its logs
stay visible separately from the setup window, and `Start App.bat` automatically opens the
app in your browser once the server responds. Keep the server window open while you use the
app; closing it (or pressing CTRL+C inside it) stops the server.

**Manual way** (with the virtual environment activated, from Step 7):
```bash
uvicorn app:app --reload --port 8000
```
Wait for a line that says `Application startup complete.`

### 14a. macOS: granting permission to run the `.command` file

If double-clicking `Start App (Mac).command` does nothing or shows a security warning:
1. Open Terminal, navigate to the project folder (`cd path/to/insightforge-ai`).
2. Run: `chmod +x "Start App (Mac).command"`
3. Try double-clicking it again. If macOS still blocks it ("cannot be opened because it is
   from an unidentified developer"), right-click the file -> **Open** -> **Open** (this only
   needs to be done once).

## 15. Open it in the browser

Go to **http://127.0.0.1:8000** in your web browser. You should see the InsightForge AI
landing page.

## 16. Test the research agent

1. Click **New Research**.
2. Type a question, e.g. *"Compare the best AI coding assistants for developers in 2026"*.
3. Choose **Quick** mode (fastest, cheapest way to test).
4. Click **Start Research**. You'll be taken to a live progress page showing each pipeline
   stage (Planning -> Searching -> Analyzing -> Cross-Checking -> Synthesizing).
5. When it finishes, you'll land on the results page with the full structured report, sources,
   and export buttons.

If you see an error mentioning "no provider configured," go back to Step 10-12 and make sure
at least one API key is set in `.env`, then restart the app.

## 17. Test provider fallback

To actually see the fallback system trigger:
1. In `.env`, deliberately set `PRIMARY_AI_PROVIDER` to a provider whose key you have **not**
   configured, e.g. if you only have an OpenAI key, set `PRIMARY_AI_PROVIDER=anthropic` and
   `FALLBACK_AI_PROVIDER=openai`.
2. Restart the app and start a new research session.
3. Because Anthropic has no key, the router immediately moves to OpenAI - you can see this in
   the terminal logs (`provider fallback succeeded: ...`) and in the **Settings** page's
   provider status.
4. Restore your `.env` to sensible values afterward.

## 18. Deploy to GitHub

```bash
git init
git add .
git commit -m "Initial commit: InsightForge AI"
git branch -M main
```
Create a new empty repository on https://github.com/new (do **not** initialize it with a
README - this project already has one), then:
```bash
git remote add origin https://github.com/<your-username>/insightforge-ai.git
git push -u origin main
```
Your `.env` file is automatically excluded (see `.gitignore`) - your API keys stay private.

## 19. Deploy to Render

1. Go to https://dashboard.render.com and sign in (GitHub login is easiest).
2. Click **New -> Blueprint**.
3. Select your `insightforge-ai` GitHub repository. Render detects `render.yaml`
   automatically and pre-fills the service configuration.
4. Click **Apply** / **Create**.

## 20. Configure Render environment variables

When Render creates the service, it will prompt you for the environment variables marked
`sync: false` in `render.yaml`: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
`TAVILY_API_KEY` (optional). Paste your keys in. If you need to change them later:
**Dashboard -> your service -> Environment -> Add/Edit variables -> Save Changes** (this triggers
an automatic redeploy).

## 21. Deploy to Railway

1. Go to https://railway.app and sign in.
2. Click **New Project -> Deploy from GitHub repo**, select `insightforge-ai`.
3. Railway detects `railway.json` and builds automatically with Nixpacks.

## 22. Configure Railway environment variables

In your Railway project: **Variables** tab -> **New Variable**, and add the same keys as
above (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.). Railway automatically
injects `$PORT`; the app already binds to `0.0.0.0:$PORT` so no changes are needed there.

## 23. Troubleshooting

> **Tip:** when running locally (`APP_ENV=development`, the default), any unexpected server
> error shows the real Python exception type and message directly in the browser/API response
> - e.g. `An unexpected server error occurred: TypeError: ...` - instead of a generic message.
> If you hit an error, copy that full text; it's the fastest way to diagnose what broke. This
> detail is automatically hidden again once `APP_ENV=production` (Render/Railway set this).

| Problem | Likely cause | Fix |
|---|---|---|
| `python: command not found` | Python not installed or not on PATH | Reinstall Python, check "Add to PATH" (Windows) |
| `pip install` fails with permission errors | Virtual environment not activated | Re-run the activate command from Step 7 |
| App starts but page won't load | Wrong port, or something else is using port 8000 | Try `uvicorn app:app --port 8001` and visit that port instead |
| "No AI provider is configured" | No API key set in `.env` | Add at least one key (Steps 10-12), restart the app |
| Research gets stuck on "Searching sources" | Corporate/school network blocking outbound search requests | Try on a personal network, or a cloud deployment (Render/Railway) |
| `ModuleNotFoundError` for a package | Dependencies not installed in the active environment | Re-run `pip install -r requirements.txt` with `venv` activated |
| macOS won't run the `.command` file | Execute permission not set / Gatekeeper block | See Step 14a |
| Changes to `.env` don't seem to apply | The server needs a restart to reload environment variables | Stop the server (Ctrl+C) and start it again |
| Render/Railway deploy fails | Missing environment variables, or `requirements.txt` install error | Check the build/deploy logs in the dashboard for the specific error |
| Browser doesn't open automatically (Windows) | PowerShell is restricted, or Chrome isn't installed at a detected path | Manually open http://localhost:8000 - the server is still running in the separate "InsightForge AI Server" window |
| `venv` stopped working after moving/sharing the project folder | Virtual environments contain absolute paths baked in and break when moved | `Start App.bat` detects and rebuilds this automatically; on macOS/Linux, delete the `venv` folder and run the start script again |

If you're stuck, re-read the relevant step above carefully - most issues are a missed
checkbox (PATH) or a forgotten `venv` activation.
