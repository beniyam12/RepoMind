from flask import Flask, request, render_template, jsonify
import chromadb, os, uuid, io, zipfile
from chromadb.utils import embedding_functions
from openai import OpenAI
from pathlib import Path

app = Flask(__name__)

# --- Chroma ---
CHROMA_DIR = os.environ.get("CHROMA_DIR", "/chroma")
client = chromadb.PersistentClient(path=CHROMA_DIR)
embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
collection = client.get_or_create_collection(name="docs", embedding_function=embed_fn)

# --- OpenAI ---
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
oai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# --- Chunking ---
def chunk_by_lines(text, win=120, overlap=20):
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        j = min(len(lines), i+win)
        out.append("\n".join(lines[i:j]))
        if j == len(lines): break
        i = max(0, j-overlap)
    return out

def chunk_by_words(text, size=500, overlap=100):
    words, out, i = text.split(), [], 0
    while i < len(words):
        j = min(len(words), i+size)
        out.append(" ".join(words[i:j]))
        if j == len(words): break
        i = max(0, j-overlap)
    return out

def choose_chunker(filename):
    ext = Path(filename).suffix.lower()
    code_exts = {".py",".js",".ts",".tsx",".java",".go",".rs",".cpp",".c",".cs",".kt",".rb",".php",".scala",".yml",".swift",".md"}
    return chunk_by_lines if ext in code_exts else chunk_by_words

# ---------- No-JS UI ----------
@app.get("/")
def ui():
    return render_template("index.html", index_msg=None, file_msg=None, answer=None)

# Handle text indexing via form
@app.post("/index_form")
def index_form():
    text = request.form.get("text","")
    if not text.strip():
        return render_template("index.html", index_msg="(empty text)", file_msg=None, answer=None)
    doc_id = str(uuid.uuid4())
    collection.add(documents=[text], ids=[doc_id])
    return render_template("index.html", index_msg=f"Indexed text as {doc_id}", file_msg=None, answer=None)

# Handle file upload via form (zip or single text file)
@app.post("/index_file_form")
def index_file_form():
    f = request.files.get("file")
    if not f:
        return render_template("index.html", index_msg=None, file_msg="No file provided", answer=None)

    project_id = str(uuid.uuid4())
    raw = f.read()

    if f.filename.lower().endswith(".zip"):
        docs, ids, metas = [], [], []
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                if name.endswith("/") or name.endswith("\\"):  # skip dirs
                    continue
                with z.open(name) as inner:
                    content = inner.read().decode("utf-8", errors="ignore")
                chunks = choose_chunker(name)(content)
                for i, ch in enumerate(chunks):
                    docs.append(ch)
                    ids.append(f"{project_id}:{name}:{i}")
                    metas.append({"project_id": project_id, "filename": name.split("/")[-1], "path": name, "chunk": i})
        if docs:
            collection.add(documents=docs, ids=ids, metadatas=metas)
        msg = f"Indexed {len({m['path'] for m in metas})} files ({len(docs)} chunks) from {f.filename}"
        return render_template("index.html", index_msg=None, file_msg=msg, answer=None)

    # single file
    content = raw.decode("utf-8", errors="ignore")
    chunks = choose_chunker(f.filename)(content)
    ids = [f"{project_id}:{f.filename}:{i}" for i in range(len(chunks))]
    metas = [{"project_id": project_id, "filename": f.filename, "path": f.filename, "chunk": i} for i in range(len(chunks))]
    if chunks:
        collection.add(documents=chunks, ids=ids, metadatas=metas)
    msg = f"Indexed {len(chunks)} chunks from {f.filename}"
    return render_template("index.html", index_msg=None, file_msg=msg, answer=None)

# Handle queries via form
@app.post("/query_form")
def query_form():
    question = request.form.get("question","")
    try:
        res = collection.query(query_texts=[question], n_results=4, include=["documents"])
        docs = (res.get("documents") or [[]])[0]
        context = "\n\n---\n\n".join(docs) if docs else ""
        prompt = f"""
        You are a repository assistant. The retrieved CONTEXT is authoritative. Any line beginning
        with “RULE:” is a binding constraint and must be followed above all else. Other lines are
        supporting documentation.

        Resolution order:
        1) RULE: lines (binding)
        2) Other context lines (supporting)
        3) General knowledge (only if the context is silent)

        If rules conflict, prefer the most specific; if still ambiguous, state the uncertainty.

        CONTEXT:
        {context}

        QUESTION:
        {question}

        ANSWER (must obey RULE: lines when present):
        """
        r = oai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role":"user","content":prompt}],
            temperature=0.2,
        )
        ans = (r.choices[0].message.content or "").strip()
        return render_template("index.html", index_msg=None, file_msg=None, answer=ans)
    except Exception as e:
        return render_template("index.html", index_msg=None, file_msg=None, answer=f"(error) {e}")

# Always JSON on errors (so even API callers don’t get HTML)
from werkzeug.exceptions import HTTPException
@app.errorhandler(Exception)
def handle_errors(e):
    code = e.code if isinstance(e, HTTPException) else 500
    return jsonify({"status":"error","type":e.__class__.__name__, "error":str(e)}), code

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
