"""ADK agent core — Phase 1.

Client Onboarding Agent: lead intake -> qualification -> proposal -> delivery handoff.
This module will hold the Google ADK (Agent Development Kit) agent definition,
Gemini-powered tools, and the onboarding workflow.

Phase 0: skeleton only — structure is real, agent logic ships in Phase 1.
"""

# TODO(phase-1): ADK agent definition (google.adk.agents.llm_agent.LLMAgent)
# TODO(phase-1): Gemini model config via env (GEMINI_API_KEY, model id)
# TODO(phase-1): Tool registry: lead intake, qualification, proposal builder, kickoff
# TODO(phase-1): Workflow graph: lead -> qualify -> propose -> delivery handoff
# TODO(phase-1): SQLite persistence (data/app.db) — never committed


def main() -> None:
    """Phase 1 entrypoint — wire the ADK agent here."""
    raise NotImplementedError("Agent logic lands in Phase 1")


if __name__ == "__main__":
    main()
