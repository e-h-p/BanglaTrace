# BanglaTrace

**Bangla document similarity screening with traceable source evidence.**

BanglaTrace is an initial research prototype for comparing Bangla writing against a supplied source collection. It retrieves candidate source sentences, optionally verifies their meaning with a selected LLM, and produces reports with source locations, sentence highlights and word-weighted matched coverage. A similarity result supports human review; it is not a verdict about academic misconduct.

## Features

- Text-based PDF/TXT sources and pasted or uploaded text to check.
- Preserved paragraphs, sentence offsets and document/page evidence.
- Lexical, dense and hybrid retrieval modes.
- OpenRouter, direct OpenAI and Anthropic verification with configurable models and prompts.
- Equivalent, partial, contradiction, unrelated and uncertain decisions.
- Key-free retrieval previews, five Bangla demo sources and sample essays.
- JSON/PDF downloads, browser printing and session report history.

## Quick start on Windows

Requirements: **Python 3.11+**, **Node.js 22.12+** with npm, and internet access for first-time dependency installation. Dense/hybrid analysis downloads LaBSE on first use.

Open PowerShell in **this folder**, containing `README.md`, `start.cmd`, `backend/` and `frontend/`, and run:

```powershell
.\start.cmd
```

You can also double-click `start.cmd`. It installs missing dependencies into `.venv/` and `frontend/node_modules/`, builds the frontend and starts one backend process. When the terminal shows **Application startup complete**, open:

**http://127.0.0.1:8000**

Keep the terminal open; **Ctrl+C** stops the app. If direct script execution is blocked, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

An API key is **not required** to start the app or run a retrieval preview.

### First demo without an API key or embedding download

1. Open **Settings -> Advanced research settings**.
2. Select **LCS + lexical prefilter only** under **Retrieval mode** and save.
3. Open **Check** and select **Mixed essay**, or enter your own text.
4. Click **Try retrieval preview** and inspect the source candidates.

The **Library** starts with five small Bangla TXT sources. Add your own sources for a relevant comparison. Preview evidence remains unverified and does not confirm matched coverage. Bundled samples are demonstrations, not an accuracy benchmark.

### LLM verification

1. In **Settings**, choose **OpenRouter**, **OpenAI / ChatGPT**, or **Claude / Anthropic**.
2. Enter that provider's API key and an available model ID. The optional model catalog can help select an ID.
3. Save settings, choose a retrieval mode, then click **Check document**.
4. Review source evidence, partial/unverified cases and diagnostics; download JSON or PDF as needed.

Verification sends shortlisted query/source pairs and the configured instruction to the selected provider. Connection tests and verification can incur provider charges. The first dense/hybrid run may download a large embedding model and requires available disk space and RAM.

## Methods and research status

| Retrieval mode | Current implementation |
| --- | --- |
| Lexical / LCS | BM25Plus prefilter and normalized character LCS reranking |
| Dense | `sentence-transformers/LaBSE` embeddings and cosine similarity |
| Hybrid | Both branches combined with Reciprocal Rank Fusion (RRF) |

All three modes can use the same LLM verifier. **Try retrieval preview** explicitly skips verification; changing the retrieval mode alone does not disable the LLM.

Engineering defaults are dense Top-10, lexical prefilter 20, lexical Top-10, and at most 6 candidates verified per query sentence. The default prompt checks names, dates, quantities and negation. Only a valid `equivalent` result confirms a match. Partial relations need review; failed or uncertain decisions remain unresolved.

Coverage is calculated as:

```text
100 x words in query sentences with at least one confirmed equivalent source
    / words in all eligible query sentences
```

Each query sentence counts once even if several sources match. Partial and unresolved cases stay outside the confirmed numerator. Incomplete reports show coverage confirmed so far. This is sentence-based coverage, not an exact copied-span estimate or plagiarism probability.

This is the **initial prototype**. The proposed research will analyse Phase 1 results to select Phase 2 methods; the current LaBSE/BM25/LCS implementation does not predetermine those choices. Calibrated non-LLM decisions and controlled E1-E5 experiments on frozen candidates are planned extensions. No benchmark accuracy is claimed for the demo.

## Configuration and data handling

UI settings are sufficient for a normal session. To change server defaults, copy the blank template and edit the resulting repository-root `.env`:

```powershell
Copy-Item .env.example .env
```

| Setting | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `openrouter`, `openai` or `anthropic` |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | Optional OpenRouter defaults |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Optional OpenAI defaults |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Optional Anthropic defaults |
| `ENABLE_DEMO_LIBRARY` | `false` starts sessions without built-in sources |
| `EMBEDDING_DEVICE` | `cpu` by default; `cuda` needs compatible PyTorch/GPU support |
| `LABSE_REVISION` | Checkpoint revision; pin a commit for reproducible research |
| `MAX_UPLOAD_MB`, `MAX_SOURCES` | Upload and source-collection limits |
| `SESSION_TTL_SECONDS` | Session lifetime; 7200 seconds by default |

Restart after changing `.env`. The template lists additional limits. `.env` is ignored by Git; `.env.example` is retained.

- Text, keys, embeddings and reports are held in session memory. Keys are not stored in browser localStorage. Sessions expire and server restarts clear them; download reports first.
- Uploads may spool temporarily under `.runtime/uploads/`; downloaded models stay cached under `.runtime/`.
- Only shortlisted pairs go to the selected provider, whose processing terms apply.
- Image-only PDFs need OCR, which is not included. Complex layouts and unusual sentence boundaries may require manual review.
- The default server binds to `127.0.0.1` and has no account authentication or durable shared session database. Use one backend worker. Remote use needs the explicit `.env.example` deployment settings and an authenticated HTTPS reverse proxy.

## Development mode

From the repository root, run setup once:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Then open two terminals in the same folder:

```powershell
# Terminal 1: FastAPI, port 8000
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1
```

```powershell
# Terminal 2: Vite, port 5173
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

Open **http://127.0.0.1:5173**. Vite proxies `/api` to FastAPI. Use `127.0.0.1` consistently for session cookies. API documentation: **http://127.0.0.1:8000/docs**.

### Manual setup on Linux/macOS

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ../backend
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Open **http://127.0.0.1:8000**. The Windows launcher is the primary local workflow; other-platform setup needs validation in its target environment.

### Optional Docker build

```text
docker build -t banglatrace .
docker run --rm -p 127.0.0.1:8000:8000 banglatrace
```

Run these commands from the repository root. The Dockerfile builds the frontend, installs CPU PyTorch and runs one backend worker. Docker deployment requires separate validation.

## Tests and local checks

After setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

This runs backend tests, frontend tests and the production build. Default tests use fixture embeddings and mocked provider transports; they do not download models or make paid API calls. `frontend/package-lock.json` pins frontend dependencies. `backend/constraints-tested.txt` records principal backend versions, not a full transitive lockfile.

With the app running at port 8000, check demo sources, assets, fonts, LCS preview and JSON export:

```powershell
.\.venv\Scripts\python.exe .\scripts\smoke_demo.py
```

This uses its own disposable session, with no model downloads or LLM calls. The summary is saved to ignored `artifacts/demo-smoke.json`.

Optional checks: `scripts/smoke_local.py` uses real LaBSE and may download weights; `scripts/smoke_openrouter.py` makes chargeable provider calls. Evaluation helpers in `backend/app/evaluation.py` require explicit human ground truth.

## Repository structure

```text
backend/app/               API, extraction, retrieval, verification and reports
backend/tests/             Backend unit and integration tests
backend/requirements.txt   Backend dependencies
frontend/src/              React/TypeScript interface, exports and tests
frontend/public/           Logo and fonts with licence notices
frontend/package-lock.json Frontend dependency lockfile
scripts/                   Setup, launch, tests and smoke checks
demo-library/              Five independent Bangla demo sources
fixtures/                  Small manual-comparison examples
.env.example               Blank configuration template
.gitignore                 Local/private/generated-file exclusions
.dockerignore              Docker build-context exclusions
Dockerfile                 Optional container build
start.cmd                  Windows quick-start launcher
README.md                  Project and run documentation
```

`.gitignore` excludes environments, `node_modules`, runtime data, compiled files, logs, reports, the generated artifact archive and local planning/validation notes. Source, tests, manifests, lockfiles, demos and bundled font licences remain available for Git.

**Use this folder as the repository root.** Git and GitHub Desktop apply `.gitignore` to untracked files. GitHub's browser upload does not automatically filter local folders using `.gitignore`; manually exclude ignored files with that route.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Port 8000 is in use | Open the existing app or stop the previous instance before starting another. |
| Missing Python/Node/npm | Install prerequisites, add them to PATH and reopen the terminal. |
| Frontend does not load | Use `start.cmd` to build the frontend before starting FastAPI. |
| First hybrid/dense run is slow | The model may be downloading/loading; use lexical preview for a lighter run. |
| Provider rejects verification | Check the provider's key, model ID, permissions and available credits. |
| Unverified or partial coverage | Inspect decisions and failures; these are not confirmed full matches. |

Bundled Anek Bangla and Noto Serif Bengali fonts include SIL Open Font License notices under `frontend/public/assets/moulik/fonts/`.
