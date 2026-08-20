"""Flash sub-agents — fast, narrow-scope classification and extraction.

Model placement rule (CLAUDE.md): the brain agent (agent.py) reasons with
the heavy model; these sub-agents do small, single-shot jobs with the fast
model. Both model ids come from env only — never hardcoded.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

# Load .env BEFORE reading FAST_MODEL — agent.py imports this module before its
# own load_dotenv() runs, so without this the env-configured fast model is ignored.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

FAST_MODEL = os.environ.get("GEMINI_FAST_MODEL", "gemini-3.5-flash")

# Factories, not module-level singletons: ADK sets a parent pointer on a
# sub-agent the moment it's attached to a parent LlmAgent, so a shared
# instance blows up the second time build_agent() runs in the same process
# (e.g. once per test, or once per CLI invocation in a long-lived process).


def build_classify_lead_agent() -> LlmAgent:
    return LlmAgent(
        name="classify_lead_agent",
        model=FAST_MODEL,
        description="Classifies a lead's priority as hot, warm, or cold.",
        instruction=(
            "You are a lead triage specialist. Given lead details (service, budget, "
            "and any urgency signals in their message), classify priority as exactly "
            "one of: 'hot', 'warm', 'cold'.\n"
            "- hot: clear budget, urgency, and good fit for our services.\n"
            "- warm: good fit but missing a clear budget or urgency signal.\n"
            "- cold: vague requirements, very low/no budget, or poor fit.\n"
            "Respond with only the single classification word, nothing else."
        ),
        output_key="lead_priority",
    )


def build_extract_info_agent() -> LlmAgent:
    return LlmAgent(
        name="extract_info_agent",
        model=FAST_MODEL,
        description="Extracts structured lead fields from raw unstructured text.",
        instruction=(
            "You extract structured lead data from raw text (an email, a form dump, "
            "a chat transcript). Output strict JSON with exactly these keys: "
            "\"name\", \"email\", \"service\", \"budget\" (a number or null). "
            "Use null for any field not actually stated in the text — never invent "
            "a value that isn't present in the source text."
        ),
        output_key="extracted_lead_info",
    )


# --- Knowledge injection -------------------------------------------------
#
# Lightweight gate, not a classifier: retrieval only runs when the lead text
# actually touches something the knowledge base covers (pricing, services,
# process, support/FAQ). Leads that mention none of these get the plain
# prompt, so we spend no retrieval work — and take no failure risk — on
# prompts that could not benefit from it.

_KNOWLEDGE_TRIGGERS = (
    "pricing",
    "cost",
    "price",
    "plan",
    "service",
    "process",
    "support",
    "refund",
    "payment",
    "how",
    "faq",
)


def needs_knowledge(query: str) -> bool:
    """True when the lead text touches a topic the knowledge base covers."""
    lowered = str(query or "").lower()
    return any(trigger in lowered for trigger in _KNOWLEDGE_TRIGGERS)


def with_knowledge(prompt: str, query: Optional[str] = None) -> str:
    """Prefix a prompt with retrieved knowledge when the gate fires.

    Args:
        prompt: the prompt that would otherwise be sent as-is.
        query: text to retrieve against — defaults to the prompt itself.

    Returns:
        The prompt unchanged when the gate does not fire, retrieval returns
        nothing, or the RAG module is unavailable; otherwise the prompt with a
        [Knowledge]...[/Knowledge] block and grounding instruction prepended.
        Never raises: this runs in a live pipeline and knowledge is an
        enhancement, so any failure degrades to the plain prompt.
    """
    text = query if query is not None else prompt
    if not needs_knowledge(text):
        return prompt
    try:
        from .rag import build_knowledge_context

        context = build_knowledge_context(text)
    except Exception:
        return prompt
    if not context:
        return prompt
    return (
        f"{context}\n\n"
        "Use the knowledge above for any claim about our pricing, services, "
        "process, or policies — it is authoritative. Never state a price or "
        "timeline that does not appear in it.\n\n"
        f"{prompt}"
    )
