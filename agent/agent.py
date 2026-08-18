"""ADK agent core — Phase 1.

Client Onboarding Agent: lead intake -> qualification -> proposal -> delivery
handoff. Model placement (CLAUDE.md hackathon requirement):
  - brain (this agent): GEMINI_BRAIN_MODEL — multi-step reasoning, proposal copy.
  - fast (sub_agents.py): GEMINI_FAST_MODEL — classification, extraction.
Model ids are never hardcoded outside the env defaults below; real values
live in .env.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from . import memory
from .sub_agents import build_classify_lead_agent, build_extract_info_agent
from .tools import create_delivery_plan, draft_proposal, intake_lead, notify_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BRAIN_MODEL_ENV = "GEMINI_BRAIN_MODEL"
DEFAULT_BRAIN_MODEL = "gemini-3.5-pro"
APP_NAME = "client_onboarding_agent"
USER_ID = "cli_user"


def build_agent() -> LlmAgent:
    """Construct the main ADK agent. Pure structure — no network/API calls."""
    brain_model = os.environ.get(BRAIN_MODEL_ENV, DEFAULT_BRAIN_MODEL)
    return LlmAgent(
        name="client_onboarding_agent",
        model=brain_model,
        description=(
            "Removes onboarding friction: carries a raw lead from first contact "
            "through qualification, a drafted proposal, and a delivery handoff plan."
        ),
        instruction=(
            "You are the Client Onboarding Agent. Given a raw lead, run this "
            "workflow: "
            "(1) call intake_lead to normalize and store it — stop and report "
            "errors if validation fails; "
            "(2) if the lead came in as unstructured text, delegate to "
            "extract_info_agent first, then classify_lead_agent to set priority; "
            "(3) call draft_proposal to build the proposal skeleton, then write "
            "real, specific overview/scope/timeline/pricing copy for the client "
            "based on their stated service and budget — never invent details "
            "they did not provide; "
            "(4) call create_delivery_plan for the handoff steps; "
            "(5) call notify_client to confirm receipt with the client. "
            "Always validate before acting."
        ),
        tools=[
            FunctionTool(intake_lead),
            FunctionTool(draft_proposal),
            FunctionTool(create_delivery_plan),
            FunctionTool(notify_client),
        ],
        sub_agents=[build_classify_lead_agent(), build_extract_info_agent()],
    )


def run_dry(lead_json: str) -> dict[str, Any]:
    """Structure-only path: build the agent, run intake_lead locally. No Gemini call."""
    agent = build_agent()
    lead_data = json.loads(lead_json)
    intake_result = intake_lead(lead_data)
    return {
        "agent": agent.name,
        "brain_model": agent.model,
        "tool_count": len(agent.tools),
        "sub_agent_count": len(agent.sub_agents),
        "sub_agents": [sa.name for sa in agent.sub_agents],
        "intake_result": intake_result,
    }


async def run_live(lead_json: str) -> str:
    """Full path: real Gemini call via the ADK Runner. Requires GEMINI_API_KEY."""
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is not set — copy .env.example to .env and fill it in."
        )

    memory.init_db()
    agent = build_agent()
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    runner = Runner(app_name=APP_NAME, agent=agent, session_service=session_service)

    user_message = types.Content(role="user", parts=[types.Part(text=f"New lead: {lead_json}")])
    final_text = ""
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=user_message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(part.text or "" for part in event.content.parts)
    return final_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Client Onboarding Agent — Phase 1 entrypoint")
    parser.add_argument("--lead", required=True, help="Raw lead as a JSON string")
    parser.add_argument(
        "--dry-run", action="store_true", help="Test agent + tool structure without calling Gemini"
    )
    args = parser.parse_args()

    if args.dry_run:
        print(json.dumps(run_dry(args.lead), indent=2, default=str))
        return

    result = asyncio.run(run_live(args.lead))
    print(result)


if __name__ == "__main__":
    main()
