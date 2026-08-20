"""Local test suite for the RAG knowledge base — no Gemini API key required.

Exercises agent/rag.py against the committed data/knowledge/*.md corpus:
retrieval quality on real client questions, the no-key keyword fallback, and
the prompt-injection context format. Run with:
    python -m agent.test_rag
or:
    python agent/test_rag.py

Prints "PASS" and exits 0 on success, "FAIL" with a traceback and exits 1
otherwise.
"""

import os
import sys
import traceback
from pathlib import Path

if __package__ in (None, ""):
    # Allow `python agent/test_rag.py` in addition to `python -m agent.test_rag`.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from agent import rag
else:
    from . import rag


def test_search_pricing() -> None:
    """A pricing question must retrieve chunks carrying the real figures."""
    hits = rag.search_knowledge("what is your pricing?")
    assert hits, "pricing query returned no chunks"
    joined = " ".join(hit["text"] for hit in hits)
    assert any(amount in joined for amount in ("$49", "$179", "$999")), joined
    assert any(hit["source"] == "pricing.md" for hit in hits), [h["source"] for h in hits]


def test_search_services() -> None:
    """A services question must retrieve the services doc's chatbot section."""
    hits = rag.search_knowledge("do you offer chatbots?")
    assert hits, "services query returned no chunks"
    services_hits = [hit for hit in hits if hit["source"] == "services.md"]
    assert services_hits, [h["source"] for h in hits]
    assert any("chatbot" in hit["text"].lower() for hit in services_hits), services_hits


def test_no_key_fallback() -> None:
    """With GEMINI_API_KEY unset, retrieval still works via the keyword index."""
    saved_key = os.environ.pop("GEMINI_API_KEY", None)
    rag.reset_cache()
    try:
        hits = rag.search_knowledge("what is your refund policy?")
        assert hits, "keyword fallback returned no chunks"
        assert all(hit["backend"] == "keyword" for hit in hits), hits
        assert any("7-day" in hit["text"] for hit in hits), hits
    finally:
        if saved_key is not None:
            os.environ["GEMINI_API_KEY"] = saved_key
        rag.reset_cache()


def test_context_format() -> None:
    """build_knowledge_context wraps real content in the [Knowledge] block."""
    context = rag.build_knowledge_context("how much does a chatbot cost?")
    assert context.startswith("[Knowledge]\n"), context[:40]
    assert context.endswith("\n[/Knowledge]"), context[-40:]

    body = context[len("[Knowledge]\n") : -len("\n[/Knowledge]")].strip()
    assert body, "knowledge block is empty"
    assert "$179" in body, body
    # An unmatchable query must yield an empty string, so callers fall back to
    # the plain prompt instead of injecting an empty block.
    assert rag.build_knowledge_context("zzzzqqqq") == ""


def run_all() -> None:
    test_search_pricing()
    test_search_services()
    test_no_key_fallback()
    test_context_format()


if __name__ == "__main__":
    try:
        run_all()
    except Exception:
        traceback.print_exc()
        print("FAIL")
        sys.exit(1)
    else:
        print("PASS")
        sys.exit(0)
