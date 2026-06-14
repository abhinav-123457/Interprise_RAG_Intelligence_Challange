"""
ingest.py — Step 2: build the hybrid search index from the manifest.

For every artefact in data/access/manifest.json we load its text, split it into
overlapping chunks, attach the artefact's access metadata (department,
sensitivity, ...) to every chunk, embed locally with sentence-transformers, and
build BOTH a FAISS (dense/semantic) and a BM25 (sparse/keyword) index. Persisted
under data/index/ so embedding is paid only once.

Run:  python ingest.py
Deps: sentence-transformers, faiss-cpu, rank-bm25, pypdf, numpy
"""
import json
import pickle
import re

import numpy as np
import faiss
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader

from config import ACCESS_DIR, INDEX_DIR, EMBED_MODEL, CHUNK_SIZE, CHUNK_OVERLAP


# ---------- Loaders: each source type -> plain text ----------
def load_pdf(path):
    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def load_csv_or_sql(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def load_json(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    return json.dumps(data, indent=2)


def load_text(artefact):
    st = artefact["source_type"]
    path = artefact["path"]
    if st == "pdf":
        return load_pdf(path)
    if st in ("csv", "sql"):
        return load_csv_or_sql(path)
    if st == "json":
        return load_json(path)
    return load_csv_or_sql(path)


# ---------- Chunking ----------
def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind(". "))
            if cut > size * 0.5:
                end = start + cut + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


# ---------- Build + persist the index ----------
def main():
    manifest_path = ACCESS_DIR / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("manifest.json not found. Run `python dataset_generator.py` first.")
    manifest = json.loads(manifest_path.read_text())

    print(f"Loading {len(manifest)} artefacts and chunking...")
    chunks = []
    for art in manifest:
        try:
            text = load_text(art)
        except Exception as e:
            print(f"  ! skipped {art['path']}: {e}")
            continue
        for i, piece in enumerate(chunk_text(text)):
            chunks.append({
                "chunk_id": f"{art['doc_id']}-c{i}",
                "doc_id": art["doc_id"],
                "text": piece,
                "department": art["department"],
                "sensitivity": art["sensitivity"],
                "source_type": art["source_type"],
                "title": art["title"],
                "path": art["path"],
            })

    if not chunks:
        raise SystemExit("No chunks produced -- is the data/ folder empty?")
    print(f"Produced {len(chunks)} chunks.")

    print(f"Embedding with {EMBED_MODEL} (first run downloads the model)...")
    model = SentenceTransformer(EMBED_MODEL)
    texts = [c["text"] for c in chunks]
    emb = model.encode(
        texts, batch_size=32, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True,
    ).astype("float32")

    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)

    bm25 = BM25Okapi([tokenize(t) for t in texts])

    faiss.write_index(index, str(INDEX_DIR / "faiss.index"))
    np.save(INDEX_DIR / "embeddings.npy", emb)
    (INDEX_DIR / "chunks.json").write_text(json.dumps(chunks, indent=2))
    with open(INDEX_DIR / "bm25.pkl", "wb") as f:
        pickle.dump(bm25, f)

    by_dept = {}
    for c in chunks:
        by_dept[c["department"]] = by_dept.get(c["department"], 0) + 1
    print("\nIndex built and saved to data/index/")
    print(f"  total chunks : {len(chunks)}")
    print(f"  vector dim   : {emb.shape[1]}")
    print("  by department:")
    for d, n in sorted(by_dept.items()):
        print(f"    {d:<12} {n}")


if __name__ == "__main__":
    main()