"""JSON CLI over the RAG retriever — the contract the Promptfoo provider grades.

    python scripts/rag_query.py "how much is a chatbot?" [top_k]

Prints a single JSON object to stdout:

    {"query": str, "count": int, "backend": str, "chunks": [{...}, ...]}

`backend` is the backend that actually served the query ("chroma", "keyword",
or "none" when nothing matched), so an eval report shows which retrieval path
was exercised. Retrieval never raises, so this exits 0 with an empty chunk
list rather than failing the eval run with a stack trace.
"""

import json
import sys
from pathlib import Path

# Allow `python scripts/rag_query.py` from the repo root without installing
# the package — the Promptfoo provider spawns this by path, not by -m.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.rag import search_knowledge  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.stderr.write('usage: python scripts/rag_query.py "<query>" [top_k]\n')
        raise SystemExit(2)

    query = sys.argv[1].strip()
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    chunks = search_knowledge(query, top_k)
    payload = {
        "query": query,
        "count": len(chunks),
        "backend": chunks[0]["backend"] if chunks else "none",
        "chunks": chunks,
    }
    # ensure_ascii keeps the payload pure ASCII so the Windows console codepage
    # cannot mangle it in transit to the Node provider.
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
