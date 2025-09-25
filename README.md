# RepoMind

RepoMind is a lightweight repository helper that uses **Retrieval-Augmented Generation (RAG)** to answer questions about your codebase. You can index whole repos (ZIP uploads), single files, and add **Repo Rules** (free-text guardrails) that the assistant will prioritize when answering.

- **Backend:** Flask  
- **Vector DB:** Chroma (SentenceTransformers `all-MiniLM-L6-v2`)  
- **LLM:** OpenAI Chat Completions (configurable via env)  

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Setup](#setup)
  - [Local (Python)](#local-python)
  - [Docker](#docker)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [Usage](#usage)
  - [Index Text (Repo Rules)](#index-text-repo-rules)
  - [Index a File or ZIP](#index-a-file-or-zip)
  - [Ask a Question](#ask-a-question)
- [API Reference (Optional JSON Endpoints)](#api-reference-optional-json-endpoints)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- Upload **ZIP archives** of repositories or **single files** for indexing.
- Add **Repo Rules** (free text) to steer the assistant’s answers.
- No-JS HTML UI (server-rendered forms) for reliability.
- Optional JSON endpoints for programmatic access / CLI.
- Persistent Chroma storage (mount a volume to keep your index).

---

## Architecture

```text
Flask (HTTP)
 ├─ /             → HTML UI (forms; no JS required)
 ├─ /index_form   → Index text (Repo Rules)
 ├─ /index_file_form → Upload single file or ZIP
 ├─ /query_form   → Ask questions against the indexed data
 ├─ /index        → JSON: index text
 ├─ /index_file   → JSON: index file/zip
 └─ /query        → JSON: ask question
```
- **Embeddings:** `all-MiniLM-L6-v2`
- **Storage:** Chroma (default path `/chroma`, configurable)

---

## Requirements

- Python 3.10+ (for local runs), or Docker
- An OpenAI API key (for Chat Completions)

Python packages (typical):
```
Flask
gunicorn
chromadb
sentence-transformers
torch
openai>=1.40.0
```
> In Docker, these are installed from `requirements.txt`.

---

## Setup

### Local (Python)

1. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set environment variables (see [Configuration](#configuration)).

4. Run the app (dev):
   ```bash
   python app.py
   ```
   The server listens on `http://localhost:8000` by default (see your app entrypoint).

### Docker

1. Build the image:
   ```bash
   docker compose build
   ```

2. Run the app:
   ```bash
   docker compose up
   ```

3. Visit the UI at `http://localhost:8000/`.

> Ensure the `templates/` and (optionally) `static/` folders are copied into the image in your `Dockerfile`.

---

## Configuration

Set the following environment variables (via shell export, `.env`, or Compose):

- `OPENAI_API_KEY` – **required**; your OpenAI API key.
- `OPENAI_MODEL` – optional; defaults to `gpt-4o-mini`.
- `CHROMA_DIR` – optional; default `/chroma`. Point this to a mounted volume if you want persistence.

Example (Linux/macOS):
```bash
export OPENAI_API_KEY=sk-...redacted...
export OPENAI_MODEL=gpt-4o-mini
export CHROMA_DIR=/chroma
```

In Docker Compose, you can mount a volume for Chroma:
```yaml
services:
  rag:
    volumes:
      - ./data/chroma:/chroma
```

---

## Running the App

- **Development (local):**
  ```bash
  python app.py
  ```

- **Production (Docker/Gunicorn):**
  ```bash
  gunicorn -w 2 -k gthread -t 120 -b 0.0.0.0:8000 app:app
  ```
  (This is typically set via `CMD` in the `Dockerfile` or `command` in `docker-compose.yml`.)

---

## Usage

### Index Text (Repo Rules)

Use the **Index text** form on the home page (`/`). The text you submit is treated as **Repo Rules** (guidelines/constraints) the assistant will prioritize when answering.

You’ll see a success message with the generated document ID in the UI.

### Index a File or ZIP

Use the **Index file** form on the home page to upload:
- A **single text-like file** (source code, `.md`, etc.), or
- A **ZIP** of your repository. The server will unpack the ZIP in memory and index each file using sensible chunking.

### Ask a Question

Use the **Query** form on the home page. The assistant retrieves the most relevant chunks (including Repo Rules) and uses them to answer.

---

## API Reference (Optional JSON Endpoints)

If you prefer programmatic access, the same functionality is exposed via JSON.

### `POST /index`
Index free text (e.g., Repo Rules).
```bash
curl -s -X POST http://localhost:8000/index \
  -H 'Content-Type: application/json' \
  -d '{"text":"Our repo rules: Use Python 3.11, write tests, and document public functions."}'
```
**Response:**
```json
{ "status": "ok", "indexed_id": "<uuid>" }
```

### `POST /index_file`
Index a single file or a ZIP.
```bash
curl -s -X POST http://localhost:8000/index_file \
  -F "file=@./repo.zip"
```
**Response:**
```json
{ "status": "ok" }
```
(Your implementation may include additional metadata like `project_id`, `chunks`, etc.)

### `POST /query`
Ask a question.
```bash
curl -s -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"How do I run tests?"}'
```
**Response:**
```json
{ "answer": "..." , "context_docs": ["..."] }
```

---

## Troubleshooting

- **“TemplateNotFound: index.html”**  
  Ensure `templates/index.html` exists **inside the running container** and your `Dockerfile` copies the `templates/` folder:
  ```dockerfile
  COPY templates ./templates
  ```

- **Got HTML instead of JSON**  
  Your HTML endpoints render templates; JSON endpoints return `application/json`. Use the JSON endpoints for programmatic calls. You can also add a global error handler to return JSON for errors.

- **No answers / null answers**  
  - Verify embeddings/models installed (Chroma + SentenceTransformers + Torch).  
  - Check `OPENAI_API_KEY` and network access in the container.  
  - Confirm you actually indexed data: `collection.count()` should be > 0.

- **ZIP uploads do nothing**  
  Make sure the upload hits `/index_file_form` or `/index_file`, and that your container has `unzip` libs available (Python’s `zipfile` is used here).

---

## License

MIT © 2025 RepoMind contributors
