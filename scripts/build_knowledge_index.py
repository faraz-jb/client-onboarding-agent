"""Build the RAG knowledge index from data/knowledge/*.md.

Usage:
    python scripts/build_knowledge_index.py
    python scripts/build_knowledge_index.py --keyword-only

With GEMINI_API_KEY set and chromadb installed, this embeds every chunk with
the Gemini embedding API and persists a Chroma collection to
CHROMA_PERSIST_DIR (default data/knowledge_db/, gitignored).

Without a key — or if embedding/Chroma fails — it falls back to writing a
deterministic pure-Python keyword inverted index (keyword_index.json) to the
same directory. agent/rag.py rebuilds that index in memory at query time, so
retrieval works offline whether or not this script has ever been run; the
artifact exists so the offline index is inspectable and the build always
produces something.

Chunking is imported from agent.rag — index and query must chunk identically.
"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.rag import (  # noqa: E402  (path setup must precede the import)
    COLLECTION_NAME,
    build_keyword_index,
    embed_texts,
    embedding_model,
    load_chunks,
    persist_dir,
)

# Gemini caps how many inputs one embed_content call accepts; batch under it.
EMBED_BATCH_SIZE = 50


def build_keyword_artifact(chunks: list, directory: Path) -> Path:
    """Write the deterministic keyword inverted index to disk. Returns its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "keyword_index.json"
    index = build_keyword_index(chunks)
    path.write_text(json.dumps(index.to_dict(), indent=2), encoding="utf-8")
    return path


def build_chroma_index(chunks: list, directory: Path) -> int:
    """Embed every chunk and persist a Chroma collection. Returns its count.

    Raises on failure — main() catches and falls back to keyword mode.
    """
    import chromadb

    directory.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(directory))
    # Rebuild from scratch so a removed or edited doc can never leave stale
    # chunks behind — the markdown is the single source of truth.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        embeddings = embed_texts([chunk.text for chunk in batch], "RETRIEVAL_DOCUMENT")
        collection.add(
            ids=[chunk.id for chunk in batch],
            documents=[chunk.text for chunk in batch],
            embeddings=embeddings,
            metadatas=[{"source": chunk.source, "heading": chunk.heading} for chunk in batch],
        )
        print(f"  embedded {min(start + len(batch), len(chunks))}/{len(chunks)} chunks")

    return collection.count()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the RAG knowledge index")
    parser.add_argument(
        "--keyword-only",
        action="store_true",
        help="Skip embeddings and build only the offline keyword index",
    )
    args = parser.parse_args()

    chunks = load_chunks()
    if not chunks:
        print("No knowledge documents found in data/knowledge/ — nothing to index.")
        return 1

    directory = persist_dir()
    sources: dict[str, int] = {}
    for chunk in chunks:
        sources[chunk.source] = sources.get(chunk.source, 0) + 1

    print(f"Knowledge base: {len(chunks)} chunks from {len(sources)} source files")
    for source in sorted(sources):
        print(f"  - {source}: {sources[source]} chunks")

    mode = "keyword"
    collection_count = 0
    if not args.keyword_only and os.environ.get("GEMINI_API_KEY"):
        print(f"Embedding with Gemini model '{embedding_model()}' -> {directory}")
        try:
            collection_count = build_chroma_index(chunks, directory)
            mode = "chroma"
        except Exception as exc:
            print(f"  vector index unavailable ({type(exc).__name__}: {exc})")
            print("  falling back to the offline keyword index")
    elif not args.keyword_only:
        print("GEMINI_API_KEY not set — building the offline keyword index instead")

    artifact = build_keyword_artifact(chunks, directory)

    print("")
    print("Index built.")
    print(f"  mode:        {mode}")
    print(f"  chunks:      {len(chunks)}")
    print(f"  sources:     {', '.join(sorted(sources))}")
    print(f"  persist dir: {directory}")
    if mode == "chroma":
        print(f"  collection:  {COLLECTION_NAME} ({collection_count} embedded chunks)")
    print(f"  keyword index artifact: {artifact.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
