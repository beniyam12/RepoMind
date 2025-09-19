from fastapi import FastAPI
from pydantic import BaseModel
import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI
import os
import uuid
from pathlib import Path
from fastapi import UploadFile, File
from typing import Optional
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse


app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def ui():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>RAG Query System</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 32px; max-width: 900px; }
    pre { background:#f6f8fa; padding:12px; border-radius:6px; }
    section { margin-bottom: 28px; }
    button { padding:6px 12px; }
  </style>
</head>
<body>
  <h1>RAG UI</h1>

  <section>
    <h2>Index text</h2>
    <textarea id="text" rows="4" cols="80" placeholder="Enter text..."></textarea><br/>
    <button id="btnIndex">Index</button>
    <pre id="indexOut"></pre>
  </section>

  <section>
    <h2>Index file</h2>
    <input type="file" id="fileInput" />
    <button id="btnFile">Upload</button>
    <pre id="fileOut"></pre>
  </section>

  <section>
    <h2>Query</h2>
    <input id="q" size="60" placeholder="Ask a question..." />
    <input id="k" type="number" value="4" min="1" max="20" />
    <button id="btnAsk">Ask</button>
    <pre id="ans"></pre>
  </section>

  <script>
    async function indexText() {
      const text = document.getElementById('text').value;
      const res = await fetch('/index', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
	const data = await res.json();
	document.getElementById('indexOut').textContent = 'Successfully indexed';
    }

    async function indexFile() {
      const f = document.getElementById('fileInput').files[0];
      if (!f) { alert('Pick a file'); return; }
      const fd = new FormData(); fd.append('file', f);
      const res = await fetch('/index_file', { method:'POST', body: fd });
	const data = await res.json();
	document.getElementById('fileOut').textContent = `Successfully indexed ${data.filename}`;	
    }

    async function ask() {
      const question = document.getElementById('q').value;
      const k = parseInt(document.getElementById('k').value || '4', 10);
      const res = await fetch('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, k })
      });
	const data = await res.json();
	document.getElementById('ans').textContent = data.answer ?? '(no answer)';
    }

    document.getElementById('btnIndex').addEventListener('click', indexText);
    document.getElementById('btnFile').addEventListener('click', indexFile);
    document.getElementById('btnAsk').addEventListener('click', ask);
  </script>
</body>
</html>
"""

# 1) Storage for vectors (Chroma) + simple local embedding model
CHROMA_DIR = os.environ.get("CHROMA_DIR", "/chroma")
client = chromadb.PersistentClient(path=CHROMA_DIR)
embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
collection = client.get_or_create_collection(name="docs", embedding_function=embed_fn)

# 2) OpenAI client for generation
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
oai = OpenAI(api_key=OPENAI_API_KEY)

class IndexIn(BaseModel):
    text: str
    id: Optional[str] = None

class QueryIn(BaseModel):
    question: str
    k: int = 4

def chunk_by_lines(text: str, win: int = 120, overlap: int = 20):
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        j = min(len(lines), i + win)
        out.append("\n".join(lines[i:j]))
        if j == len(lines):
            break
        i = j - overlap
        if i < 0:
            i = 0
    return out


def chunk_by_words(text: str, size: int = 500, overlap: int = 100):
    words = text.split()
    out = []
    i = 0
    while i < len(words):
        j = min(len(words), i + size)
        out.append(" ".join(words[i:j]))
        if j == len(words):
            break
        i = j - overlap
        if i < 0:
            i = 0
    return out


def choose_chunker(filename: str):
    ext = Path(filename).suffix.lower()
    code_exts = {".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs", ".cpp", ".c", ".cs", ".kt", ".rb", ".php", ".scala", ".yml", ".swift", ".md"}
    if ext in code_exts:
        return chunk_by_lines
    return chunk_by_words


@app.post("/index_file")
async def index_file(file: UploadFile = File(...)):
    try:
        doc_id_base = str(uuid.uuid4())
        content = (await file.read()).decode("utf-8", errors="ignore")
        chunker = choose_chunker(file.filename)
        chunks = chunker(content)

        ids = [f"{doc_id_base}:{i}" for i in range(len(chunks))]
        collection.add(
            documents=chunks,
            ids=ids,
            metadatas=[{"filename": file.filename, "chunk": i} for i in range(len(chunks))]
        )
        return {"status": "ok", "indexed_ids": ids, "chunks": len(chunks), "filename": file.filename}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}

@app.post("/index")
def index_doc(payload: IndexIn):
    doc_id = payload.id or str(uuid.uuid4())
    collection.add(documents=[payload.text], ids=[doc_id])
    return {"status": "ok", "indexed_id": doc_id}

@app.post("/query")
def query(payload: QueryIn):
    results = collection.query(query_texts=[payload.question], n_results=payload.k)
    docs = results.get("documents", [[]])[0]

    context = "\n\n---\n\n".join(docs) if docs else "No context found."
    prompt = (
        "Use the context to answer. If context is missing, use your own knowledge base\n\n"
        f"Context:\n{context}\n\nQuestion: {payload.question}\nAnswer:"
    )

    resp = oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    answer = resp.choices[0].message.content.strip()
    return {"answer": answer, "context_docs": docs}
