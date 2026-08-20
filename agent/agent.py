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
from typing import Any, Optional

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from . import memory
from .sub_agents import build_classify_lead_agent, build_extract_info_agent, with_knowledge
from .tools import (
    create_delivery_plan,
    draft_proposal,
    finalize_proposal,
    intake_lead,
    notify_client,
    search_knowledge,
    update_lead_priority,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BRAIN_MODEL_ENV = "GEMINI_BRAIN_MODEL"
DEFAULT_BRAIN_MODEL = "gemini-3.1-pro-preview"
APP_NAME = "client_onboarding_agent"
USER_ID = "cli_user"
_VALID_PRIORITIES = ("hot", "warm", "cold")


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
            "extract_info_agent first, then classify_lead_agent to set priority, "
            "then call update_lead_priority to persist it; "
            "(3) call draft_proposal to build the proposal skeleton, write "
            "real, specific overview/scope/timeline/pricing copy for the client "
            "based on their stated service and budget — never invent details "
            "they did not provide — then call finalize_proposal to persist it; "
            "(4) call create_delivery_plan for the handoff steps; "
            "(5) call notify_client to confirm receipt with the client. "
            "Always validate before acting. Whenever the lead asks about "
            "price, what we offer, timelines, or policy, call search_knowledge "
            "first and answer only from what it returns — never quote a figure "
            "from memory."
        ),
        tools=[
            FunctionTool(intake_lead),
            FunctionTool(update_lead_priority),
            FunctionTool(draft_proposal),
            FunctionTool(finalize_proposal),
            FunctionTool(create_delivery_plan),
            FunctionTool(notify_client),
            FunctionTool(search_knowledge),
        ],
        sub_agents=[build_classify_lead_agent(), build_extract_info_agent()],
    )


def _build_proposal_writer_agent() -> LlmAgent:
    """Brain-tier, tool-less agent: writes final proposal copy as strict JSON.

    Kept separate from build_agent() so invoking it (Runner, single-shot) can
    never trigger autonomous tool calls — process_lead() controls persistence
    itself via finalize_proposal.
    """
    brain_model = os.environ.get(BRAIN_MODEL_ENV, DEFAULT_BRAIN_MODEL)
    return LlmAgent(
        name="proposal_writer_agent",
        model=brain_model,
        description="Writes real, specific proposal copy for a qualified lead.",
        instruction=(
            "You write client proposals. Given lead details and priority, output "
            "STRICT JSON with exactly these keys: overview, scope, timeline, pricing "
            "(all strings, no nesting). Base every claim only on the lead's stated "
            "service and budget — never invent details the client did not provide. "
            "Respond with the JSON object only — no markdown fences, no prose "
            "outside the JSON."
        ),
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


async def _run_single_agent(agent: LlmAgent, prompt: str, app_name: str) -> str:
    """Run one tool-less LlmAgent to completion and return its final text."""
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=app_name, user_id=USER_ID)
    runner = Runner(app_name=app_name, agent=agent, session_service=session_service)

    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    async for event in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(part.text or "" for part in event.content.parts)
    return final_text


def _strip_code_fence(text: str) -> str:
    """Strip a ```/```json wrapper some models add despite JSON-only instructions."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _classify_lead_offline(lead: dict[str, Any]) -> str:
    """Deterministic, non-LLM priority heuristic — used without GEMINI_API_KEY."""
    budget = lead.get("budget")
    service = str(lead.get("service") or "").strip().lower()
    if budget is not None and budget >= 3000 and service not in ("", "unspecified"):
        return "hot"
    if budget is not None and budget > 0:
        return "warm"
    return "cold"


async def _classify_lead_live(lead: dict[str, Any]) -> str:
    """Real classification via the classify_lead_agent Flash sub-agent."""
    agent = build_classify_lead_agent()
    prompt = (
        f"Lead details — name: {lead['name']}, service: {lead['service']}, "
        f"budget: {lead['budget']}, raw intake: {lead['raw_json']}. Classify this lead."
    )
    # Ground the fit judgement in what we actually sell and charge — a $200
    # budget reads very differently once the model can see the real price list.
    prompt = with_knowledge(prompt, f"{lead['service']} {lead['raw_json']}")
    text = (await _run_single_agent(agent, prompt, "classify_lead")).strip().lower()
    if text in _VALID_PRIORITIES:
        return text
    for candidate in _VALID_PRIORITIES:
        if candidate in text:
            return candidate
    return _classify_lead_offline(lead)


async def _expand_proposal_live(lead: dict[str, Any], priority: str) -> Optional[dict[str, str]]:
    """Real proposal copy via the brain-tier proposal_writer_agent. None on parse failure."""
    agent = _build_proposal_writer_agent()
    prompt = (
        f"Lead — name: {lead['name']}, service: {lead['service']}, budget: {lead['budget']}, "
        f"priority: {priority}. Write the proposal JSON now."
    )
    # Proposals quote real prices and timelines, so retrieve unconditionally
    # here rather than through the keyword gate — every proposal is a pricing
    # question whether or not the lead phrased it as one.
    prompt = with_knowledge(prompt, f"{lead['service']} pricing process timeline")
    text = await _run_single_agent(agent, prompt, "proposal_writer")
    try:
        data = json.loads(_strip_code_fence(text))
        return {
            "overview": str(data.get("overview") or "").strip(),
            "scope": str(data.get("scope") or "").strip(),
            "timeline": str(data.get("timeline") or "").strip(),
            "pricing": str(data.get("pricing") or "").strip(),
        }
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def process_lead(lead_id: int, force_dry_run: bool = False) -> dict[str, Any]:
    """Full pipeline for an existing lead: classify -> proposal -> delivery -> notify.

    Uses real Gemini calls (classify_lead_agent + proposal_writer_agent) when
    GEMINI_API_KEY is set and force_dry_run is False; otherwise runs a
    deterministic offline path so the DB/API plumbing is testable without a
    key. Either way every step writes an agent_log audit row and moves
    leads.status through: processing -> classified -> proposal_ready.
    """
    conn = memory.init_db()
    try:
        lead = memory.get_lead(conn, lead_id)
    finally:
        conn.close()
    if lead is None:
        return {"ok": False, "errors": [f"lead {lead_id} not found"]}

    use_live = bool(os.environ.get("GEMINI_API_KEY")) and not force_dry_run

    conn = memory.init_db()
    try:
        memory.update_lead_status(conn, lead_id, "processing")
    finally:
        conn.close()

    # 1. Classify — live Gemini when available, offline heuristic as a
    # hard fallback so a temporary 503/overload never crashes the pipeline.
    if use_live:
        try:
            priority = asyncio.run(_classify_lead_live(lead))
        except Exception:
            priority = _classify_lead_offline(lead)
    else:
        priority = _classify_lead_offline(lead)
    priority_result = update_lead_priority(lead_id, priority)
    if not priority_result["ok"]:
        return priority_result

    conn = memory.init_db()
    try:
        memory.update_lead_status(conn, lead_id, "classified")
    finally:
        conn.close()

    # 2. Proposal — skeleton first, then expand with real copy when live.
    proposal_result = draft_proposal(lead_id)
    if not proposal_result["ok"]:
        return proposal_result

    if use_live:
        try:
            expanded = asyncio.run(_expand_proposal_live(lead, priority))
        except Exception:
            expanded = None
    else:
        expanded = None
    final_content = expanded or proposal_result["proposal"]
    finalize_result = finalize_proposal(proposal_result["proposal_id"], **final_content)
    if not finalize_result["ok"]:
        return finalize_result

    conn = memory.init_db()
    try:
        memory.update_lead_status(conn, lead_id, "proposal_ready")
    finally:
        conn.close()

    # 3. Delivery plan.
    delivery_result = create_delivery_plan(lead_id)
    if not delivery_result["ok"]:
        return delivery_result

    # 4. Notify.
    budget = lead.get("budget")
    budget_display = f"${budget:,.0f}" if budget is not None else "budget TBD"
    message = f"\U0001f195 Lead: {lead['name']} ({lead['service']}, {budget_display}) — priority: {priority}"
    notify_result = notify_client(lead_id, message)

    return {
        "ok": True,
        "lead_id": lead_id,
        "mode": "live" if use_live else "offline",
        "priority": priority,
        "proposal_id": proposal_result["proposal_id"],
        "proposal_source": "gemini" if expanded else "skeleton",
        "delivery_plan_id": delivery_result["delivery_plan_id"],
        "notify": notify_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Client Onboarding Agent — CLI entrypoint")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--lead", help="Raw lead as a JSON string (intake-only path)")
    mode.add_argument(
        "--lead-id",
        type=int,
        help="Existing lead id — runs classify -> proposal -> delivery -> notify",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force the offline path — no Gemini calls, no Telegram send",
    )
    args = parser.parse_args()

    if args.lead_id is not None:
        result = process_lead(args.lead_id, force_dry_run=args.dry_run)
        print(json.dumps(result, indent=2, default=str))
        return

    if args.dry_run:
        print(json.dumps(run_dry(args.lead), indent=2, default=str))
        return

    result = asyncio.run(run_live(args.lead))
    print(result)


if __name__ == "__main__":
    main()
