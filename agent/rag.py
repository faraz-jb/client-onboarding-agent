"""RAG knowledge base — retrieval over data/knowledge/*.md.

Two backends behind one interface:
  - Chroma vector store (data/knowledge_db, built by
    scripts/build_knowledge_index.py) with Gemini embeddings — used when the
    store exists, chromadb is importable, and GEMINI_API_KEY is set.
  - A pure-Python keyword inverted index built in memory from the markdown
    source — used otherwise.

Graceful degradation is the whole point: this module runs inside a LIVE
onboarding pipeline, so no missing key, missing dependency, or corrupt index
may raise out of search_knowledge()/build_knowledge_context(). Every failure
path falls back to keyword mode, and keyword mode depends only on the stdlib
plus the committed markdown.
"""

import math
import os
import re
import sys
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "knowledge"
DEFAULT_PERSIST_DIR = "data/knowledge_db"
# Verified against the live API: text-embedding-004 is retired and returns 404
# on v1beta. gemini-embedding-001 is the current GA embedding model.
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
COLLECTION_NAME = "onboarding_knowledge"

# Max characters per chunk before a long section is split across chunks.
MAX_CHUNK_CHARS = 900

# Relevance floor for the vector backend: the largest cosine distance a
# chunk may sit at and still count as an answer. Measured against this
# corpus, real client questions retrieve their best chunk at 0.22-0.29,
# while queries with no answer here bottom out around 0.38 - so the cutoff
# sits between the two populations rather than at an arbitrary round number.
MAX_CHROMA_DISTANCE = 0.33

# Terms that carry no retrieval signal in client questions.
_STOPWORDS = frozenset(
    """
    a an and are as at be been but by can do does doing for from get give had has have
    how i if in into is it its me my of on or our ours so that the their them then there
    these they this to us was we were what when where which who why will with would you
    your yours am about any tell please could should much many
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9$][a-z0-9$/.-]*")


def persist_dir() -> Path:
    """Absolute path of the Chroma store (CHROMA_PERSIST_DIR, else the default)."""
    configured = (os.environ.get("CHROMA_PERSIST_DIR") or "").strip() or DEFAULT_PERSIST_DIR
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


def embedding_model() -> str:
    """Gemini embedding model id from env — never hardcoded at the call site."""
    return (os.environ.get("GEMINI_EMBEDDING_MODEL") or "").strip() or DEFAULT_EMBEDDING_MODEL


# --------------------------------------------------------------------------
# Chunking — deterministic, dependency-free, shared with the index builder.
# --------------------------------------------------------------------------


@dataclass
class Chunk:
    """One retrievable unit of knowledge."""

    id: str
    text: str
    source: str
    heading: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "source": self.source, "heading": self.heading}


def chunk_markdown(markdown: str, source: str) -> list[Chunk]:
    """Split markdown into chunks by heading, then by paragraph when oversized.

    Each chunk carries its heading breadcrumb ("Pricing > AI Chatbot") as a
    first line so section context survives retrieval — those heading terms are
    part of what both backends match against, and part of what the LLM reads.
    """
    chunks: list[Chunk] = []
    stack: list[str] = []  # heading titles by depth
    paragraphs: list[str] = []

    def emit(breadcrumb: str, buffer: list[str]) -> None:
        body = "\n\n".join(buffer).strip()
        if not body:
            return
        text = f"{breadcrumb}\n\n{body}" if breadcrumb else body
        chunks.append(
            Chunk(id=f"{source}::{len(chunks)}", text=text, source=source, heading=breadcrumb)
        )

    def flush() -> None:
        if not paragraphs:
            return
        breadcrumb = " > ".join(stack)
        buffer: list[str] = []
        size = 0
        for paragraph in paragraphs:
            # Start a new chunk when this paragraph would overflow, but never
            # emit an empty one — an oversized single paragraph rides alone.
            if buffer and size + len(paragraph) > MAX_CHUNK_CHARS:
                emit(breadcrumb, buffer)
                buffer, size = [], 0
            buffer.append(paragraph)
            size += len(paragraph)
        if buffer:
            emit(breadcrumb, buffer)
        paragraphs.clear()

    block: list[str] = []
    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if heading:
            if block:
                paragraphs.append("\n".join(block).strip())
                block = []
            flush()
            level = len(heading.group(1))
            del stack[level - 1 :]
            stack.append(heading.group(2).strip())
            continue
        if line.strip():
            block.append(line.rstrip())
        elif block:
            paragraphs.append("\n".join(block).strip())
            block = []
    if block:
        paragraphs.append("\n".join(block).strip())
    flush()
    return chunks


def load_chunks(knowledge_dir: Optional[Path] = None) -> list[Chunk]:
    """Chunk every .md file in the knowledge dir, sorted for a stable index."""
    directory = knowledge_dir or KNOWLEDGE_DIR
    chunks: list[Chunk] = []
    if not directory.is_dir():
        return chunks
    for path in sorted(directory.glob("*.md")):
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError:
            continue
        chunks.extend(chunk_markdown(markdown, path.name))
    return chunks


# --------------------------------------------------------------------------
# Keyword backend — pure-Python inverted index with tf-idf scoring.
# --------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Lowercase, drop stopwords, and normalize simple plurals.

    Money figures survive intact ("$179", "$49/mo") because '$' and '/' are
    part of the token pattern — those are exactly the facts clients ask for.
    """
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        token = raw.strip(".-/")
        if not token:
            continue
        # Hyphenated and slashed compounds are indexed whole *and* split, so a
        # client asking "white label" still matches the doc's "white-label".
        for part in [token] + [p for p in re.split(r"[-/]", token) if p and p != token]:
            if part in _STOPWORDS:
                continue
            tokens.append(part)
            # Cheap singularization so "chatbots" matches "chatbot".
            if len(part) > 3 and part.endswith("s") and not part.endswith("ss"):
                tokens.append(part[:-1])
    return tokens


@dataclass
class KeywordIndex:
    """Inverted index: term -> {chunk position -> term frequency}."""

    chunks: list[Chunk]
    postings: dict[str, dict[int, int]] = field(default_factory=dict)
    lengths: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form, for the builder's offline artifact."""
        return {
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "postings": {term: dict(posting) for term, posting in self.postings.items()},
            "lengths": self.lengths,
        }


def build_keyword_index(chunks: list[Chunk]) -> KeywordIndex:
    """Build the inverted index. Deterministic — same input, same index."""
    index = KeywordIndex(chunks=chunks)
    for position, chunk in enumerate(chunks):
        # The source stem is indexed as a term so "pricing"/"faq" style queries
        # match the right document even when the word is absent from the body.
        # Heading terms are indexed twice: a section titled "Refund policy"
        # is a stronger answer to a refund question than one that merely
        # mentions refunds in passing.
        terms = (
            tokenize(chunk.text) + tokenize(chunk.heading) + tokenize(Path(chunk.source).stem)
        )
        index.lengths.append(max(len(terms), 1))
        for term, frequency in Counter(terms).items():
            index.postings.setdefault(term, {})[position] = frequency
    return index


def keyword_search(index: KeywordIndex, query: str, top_k: int) -> list[dict[str, Any]]:
    """Score chunks against the query with tf-idf over the inverted index.

    Requires at least one shared term between query and chunk - a query that
    overlaps the corpus nowhere retrieves nothing rather than the top-k of an
    all-zero ranking.
    """
    query_terms = tokenize(query)
    if not query_terms or not index.chunks:
        return []

    total = len(index.chunks)
    scores: dict[int, float] = {}
    for term in set(query_terms):
        posting = index.postings.get(term)
        if not posting:
            continue
        idf = math.log(1 + total / len(posting))
        for position, frequency in posting.items():
            # Length-normalized tf keeps a long section from outranking a
            # short, precise one purely on word count.
            scores[position] = scores.get(position, 0.0) + idf * (
                frequency / index.lengths[position]
            )

    # Relevance floor: no query term appears anywhere in the corpus, so there
    # is nothing to answer with. Returning the "least bad" chunks here would
    # put irrelevant text in front of the model as if it were an answer.
    if not scores:
        return []

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    return [
        {
            "text": index.chunks[position].text,
            "source": index.chunks[position].source,
            "heading": index.chunks[position].heading,
            "score": round(score, 6),
            "backend": "keyword",
        }
        for position, score in ranked
    ]


# --------------------------------------------------------------------------
# Chroma backend — Gemini embeddings over the persisted vector store.
# --------------------------------------------------------------------------


def embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
    """Embed texts with the Gemini embedding API. Raises on any failure.

    Callers in this module always catch — a dead embedding call degrades to
    keyword mode rather than breaking the pipeline.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.embed_content(
        model=embedding_model(),
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    return [list(embedding.values) for embedding in response.embeddings]


def open_chroma_collection() -> Optional[Any]:
    """Return the persisted Chroma collection, or None if it is unusable."""
    directory = persist_dir()
    if not directory.is_dir():
        return None
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(directory))
        collection = client.get_collection(COLLECTION_NAME)
        return collection if collection.count() else None
    except Exception:
        return None


def chroma_search(collection: Any, query: str, top_k: int) -> list[dict[str, Any]]:
    """Vector search. Returns [] on any failure, or when nothing clears the
    relevance floor, so the caller can fall back."""
    try:
        query_embedding = embed_texts([query], "RETRIEVAL_QUERY")[0]
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    # Relevance floor. A vector store always hands back its nearest neighbours
    # however far away they are, so an unanswerable query still comes back with
    # a full top-k. Judge the query by its *best* chunk: once that one clears
    # the floor the query is known-answerable and its tail is worth keeping.
    # No distances (an unexpected response shape) means no way to judge - drop
    # through to the keyword backend rather than trust the hits blindly.
    measured = [distance for distance in distances if distance is not None]
    if not measured or min(measured) > MAX_CHROMA_DISTANCE:
        return []

    hits: list[dict[str, Any]] = []
    for position, document in enumerate(documents):
        metadata = metadatas[position] if position < len(metadatas) else {}
        distance = distances[position] if position < len(distances) else None
        hits.append(
            {
                "text": document,
                "source": (metadata or {}).get("source", "unknown"),
                "heading": (metadata or {}).get("heading", ""),
                # Chroma returns a distance; invert it so higher is better,
                # matching the keyword backend's score direction.
                "score": round(1.0 / (1.0 + distance), 6) if distance is not None else 0.0,
                "backend": "chroma",
            }
        )
    return hits


# --------------------------------------------------------------------------
# Public API — lazy, cached, never raises.
# --------------------------------------------------------------------------

_LOCK = threading.Lock()
_keyword_index: Optional[KeywordIndex] = None
_collection: Optional[Any] = None
_collection_loaded = False


def _get_keyword_index() -> KeywordIndex:
    """Lazy-build the in-memory keyword index once per process."""
    global _keyword_index
    with _LOCK:
        if _keyword_index is None:
            _keyword_index = build_keyword_index(load_chunks())
        return _keyword_index


def _get_collection() -> Optional[Any]:
    """Lazy-open the Chroma collection once per process. None => keyword mode."""
    global _collection, _collection_loaded
    with _LOCK:
        if not _collection_loaded:
            _collection_loaded = True
            _collection = open_chroma_collection() if os.environ.get("GEMINI_API_KEY") else None
        return _collection


def reset_cache() -> None:
    """Drop cached backends — used by tests that flip env vars mid-process."""
    global _keyword_index, _collection, _collection_loaded
    with _LOCK:
        _keyword_index = None
        _collection = None
        _collection_loaded = False


def search_knowledge(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Retrieve the top-k knowledge chunks answering a question.

    Searches the AI Invention knowledge base (pricing, services, onboarding
    process, FAQ) and returns the most relevant passages.

    Args:
        query: natural-language question, e.g. "what does a chatbot cost?".
        top_k: number of chunks to return (default 3).

    Returns:
        A list of {text, source, heading, score, backend} dicts, best first.
        Empty when nothing matched, including when the corpus holds no answer
        to the question — callers must handle []. Never raises: a vector-search
        failure silently degrades to keyword search.
    """
    try:
        query = str(query or "").strip()
        top_k = max(1, int(top_k))
        if not query:
            return []

        collection = _get_collection()
        if collection is not None:
            hits = chroma_search(collection, query, top_k)
            if hits:
                return hits
        return keyword_search(_get_keyword_index(), query, top_k)
    except Exception:
        # Absolute backstop: retrieval is an enhancement, never a failure mode.
        return []


def build_knowledge_context(query: str, top_k: int = 3) -> str:
    """Format retrieved chunks as a prompt-injectable knowledge block.

    Args:
        query: the question to retrieve against.
        top_k: number of chunks to include (default 3).

    Returns:
        "[Knowledge]\\n<chunk>\\n---\\n<chunk>\\n[/Knowledge]", or "" when
        nothing was retrieved (callers then use the plain prompt unchanged).
    """
    hits = search_knowledge(query, top_k)
    if not hits:
        return ""
    body = "\n---\n".join(hit["text"].strip() for hit in hits)
    return f"[Knowledge]\n{body}\n[/Knowledge]"


def main() -> None:
    """CLI: `python -m agent.rag "<query>"` — prints the knowledge block.

    This is the contract the Promptfoo RAG provider grades against.
    """
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        sys.stderr.write('usage: python -m agent.rag "<query>"\n')
        raise SystemExit(2)
    context = build_knowledge_context(query) or "[Knowledge]\n[/Knowledge]"
    sys.stdout.write(context + "\n")


if __name__ == "__main__":
    main()
