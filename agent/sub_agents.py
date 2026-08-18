"""Flash sub-agents — fast, narrow-scope classification and extraction.

Model placement rule (CLAUDE.md): the brain agent (agent.py) reasons with
the heavy model; these sub-agents do small, single-shot jobs with the fast
model. Both model ids come from env only — never hardcoded.
"""

import os

from google.adk.agents import LlmAgent

FAST_MODEL = os.environ.get("GEMINI_FAST_MODEL", "gemini-3-flash")

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
