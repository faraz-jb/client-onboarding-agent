"""ADK tools for the Client Onboarding Agent.

Plain, type-hinted functions — wrapped in google.adk.tools.FunctionTool at
registration time in agent.py. Kept as plain functions here too so they can
be called directly (no LLM, no network) for local dry-run and test paths.

Every tool validates its own input and writes an agent_log audit row via
memory.py — security-first rule from CLAUDE.md: no unaudited state changes.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from . import memory, rag

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ACTOR = "client_onboarding_agent"
_VALID_PRIORITIES = {"hot", "warm", "cold"}


def intake_lead(lead_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize, validate, and store a raw lead.

    Args:
        lead_data: Raw lead fields. Expected keys: name (str), email (str),
            service (str, optional — defaults to "unspecified"),
            budget (number, optional).

    Returns:
        On success: {"ok": True, "lead_id": int, "lead": {...normalized...}}.
        On failure: {"ok": False, "errors": [str, ...]}.
    """
    errors: list[str] = []

    name = str(lead_data.get("name", "")).strip()
    email = str(lead_data.get("email", "")).strip().lower()
    service = str(lead_data.get("service", "")).strip() or "unspecified"
    budget_raw = lead_data.get("budget")
    budget: Optional[float] = None

    if not name:
        errors.append("name is required")
    if not email or not _EMAIL_RE.match(email):
        errors.append("a valid email is required")
    if budget_raw is not None:
        try:
            budget = float(budget_raw)
            if budget < 0:
                errors.append("budget must be >= 0")
        except (TypeError, ValueError):
            errors.append("budget must be numeric")

    conn = memory.init_db()
    try:
        if errors:
            memory.log_action(
                conn, _ACTOR, "intake_lead_rejected", target=email or name, detail="; ".join(errors)
            )
            return {"ok": False, "errors": errors}

        lead_id = memory.insert_lead(conn, name, email, service, budget, lead_data)
        memory.log_action(conn, _ACTOR, "intake_lead", target=str(lead_id))
        return {
            "ok": True,
            "lead_id": lead_id,
            "lead": {"name": name, "email": email, "service": service, "budget": budget},
        }
    finally:
        conn.close()


def update_lead_priority(lead_id: int, priority: str) -> dict[str, Any]:
    """Set a stored lead's priority classification (hot/warm/cold).

    Args:
        lead_id: id of a lead previously stored via intake_lead.
        priority: one of "hot", "warm", "cold" (case-insensitive).

    Returns:
        On success: {"ok": True, "lead_id": int, "priority": str}.
        On failure: {"ok": False, "errors": [str, ...]}.
    """
    normalized = str(priority).strip().lower()
    conn = memory.init_db()
    try:
        if normalized not in _VALID_PRIORITIES:
            memory.log_action(
                conn,
                "classify_lead_agent",
                "classify_lead_rejected",
                target=str(lead_id),
                detail=f"invalid priority: {priority!r}",
            )
            return {"ok": False, "errors": [f"priority must be one of {sorted(_VALID_PRIORITIES)}"]}

        lead = memory.get_lead(conn, lead_id)
        if lead is None:
            memory.log_action(
                conn, "classify_lead_agent", "classify_lead_rejected", target=str(lead_id), detail="lead not found"
            )
            return {"ok": False, "errors": [f"lead {lead_id} not found"]}

        memory.update_lead_priority(conn, lead_id, normalized)
        memory.log_action(conn, "classify_lead_agent", "classify_lead", target=str(lead_id), detail=normalized)
        return {"ok": True, "lead_id": lead_id, "priority": normalized}
    finally:
        conn.close()


def draft_proposal(lead_id: int) -> dict[str, Any]:
    """Build and store a proposal skeleton for a stored lead.

    Generates the four standard sections (overview, scope, timeline,
    pricing). The brain agent is expected to expand these into full client
    copy — this tool only produces and persists the structure.

    Args:
        lead_id: id of a lead previously stored via intake_lead.

    Returns:
        On success: {"ok": True, "proposal_id": int, "proposal": {...}}.
        On failure: {"ok": False, "errors": [str, ...]}.
    """
    conn = memory.init_db()
    try:
        lead = memory.get_lead(conn, lead_id)
        if lead is None:
            memory.log_action(
                conn, _ACTOR, "draft_proposal_rejected", target=str(lead_id), detail="lead not found"
            )
            return {"ok": False, "errors": [f"lead {lead_id} not found"]}

        overview = f"Proposal for {lead['name']} — {lead['service']} engagement."
        scope = f"Scope to be defined for the {lead['service']} service based on stated requirements."
        timeline = "Discovery -> Build -> Review -> Handover."
        pricing = (
            f"Budget target: {lead['budget']}"
            if lead["budget"] is not None
            else "Pricing to be scoped with the client."
        )

        proposal_id = memory.insert_proposal(conn, lead_id, overview, scope, timeline, pricing)
        memory.log_action(conn, _ACTOR, "draft_proposal", target=str(lead_id), detail=str(proposal_id))
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "proposal": {"overview": overview, "scope": scope, "timeline": timeline, "pricing": pricing},
        }
    finally:
        conn.close()


def finalize_proposal(proposal_id: int, overview: str, scope: str, timeline: str, pricing: str) -> dict[str, Any]:
    """Replace a proposal's skeleton content with final copy and mark it ready.

    Called after the brain agent expands overview/scope/timeline/pricing into
    real, client-specific copy (Phase 3). Offline/dry-run callers may pass the
    skeleton content straight through — it still marks the proposal ready.

    Args:
        proposal_id: id of a proposal previously created via draft_proposal.
        overview: final overview section.
        scope: final scope section.
        timeline: final timeline section.
        pricing: final pricing section.

    Returns:
        On success: {"ok": True, "proposal_id": int}.
        On failure: {"ok": False, "errors": [str, ...]}.
    """
    conn = memory.init_db()
    try:
        updated = memory.update_proposal(
            conn, proposal_id, str(overview).strip(), str(scope).strip(), str(timeline).strip(), str(pricing).strip()
        )
        if not updated:
            memory.log_action(
                conn,
                "proposal_writer_agent",
                "finalize_proposal_rejected",
                target=str(proposal_id),
                detail="proposal not found",
            )
            return {"ok": False, "errors": [f"proposal {proposal_id} not found"]}

        memory.log_action(conn, "proposal_writer_agent", "finalize_proposal", target=str(proposal_id))
        return {"ok": True, "proposal_id": proposal_id}
    finally:
        conn.close()


def create_delivery_plan(lead_id: int) -> dict[str, Any]:
    """Build and store the standard delivery plan for a stored lead.

    Steps: discovery -> build -> review -> handover.

    Args:
        lead_id: id of a lead previously stored via intake_lead.

    Returns:
        On success: {"ok": True, "delivery_plan_id": int, "steps": [...]}.
        On failure: {"ok": False, "errors": [str, ...]}.
    """
    conn = memory.init_db()
    try:
        lead = memory.get_lead(conn, lead_id)
        if lead is None:
            memory.log_action(
                conn, _ACTOR, "create_delivery_plan_rejected", target=str(lead_id), detail="lead not found"
            )
            return {"ok": False, "errors": [f"lead {lead_id} not found"]}

        steps = [
            {
                "step": "discovery",
                "description": "Confirm requirements and success criteria with the client.",
                "status": "pending",
            },
            {
                "step": "build",
                "description": f"Deliver the {lead['service']} work.",
                "status": "pending",
            },
            {
                "step": "review",
                "description": "Client review and revision pass.",
                "status": "pending",
            },
            {
                "step": "handover",
                "description": "Final handover, documentation, and access transfer.",
                "status": "pending",
            },
        ]

        plan_id = memory.insert_delivery_plan(conn, lead_id, steps)
        memory.log_action(conn, _ACTOR, "create_delivery_plan", target=str(lead_id), detail=str(plan_id))
        return {"ok": True, "delivery_plan_id": plan_id, "steps": steps}
    finally:
        conn.close()


def _send_telegram(message: str) -> tuple[bool, str]:
    """Send a message via the Telegram Bot API. Returns (sent, detail).

    Uses stdlib urllib only — no new dependency for one HTTP call. Requires
    TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env; without them the caller
    falls back to the console-log stub.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "no_telegram_credentials"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status == 200, "sent"
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        return False, f"telegram_error: {exc}"


def notify_client(lead_id: int, message: str) -> dict[str, Any]:
    """Notify the client. Sends a real Telegram message when credentials are
    configured (AI Invention Receptionist bot pattern); without them, falls
    back to a console-log stub. Either way, writes an audit row.

    Args:
        lead_id: id of the lead to notify.
        message: message body to send.

    Returns:
        On success: {"ok": True, "status": "sent_telegram" | "logged_stub", "lead_id": int, "message": str}.
        On failure: {"ok": False, "errors": [str, ...]}.
    """
    message = str(message).strip()
    conn = memory.init_db()
    try:
        lead = memory.get_lead(conn, lead_id)
        if lead is None:
            memory.log_action(
                conn, _ACTOR, "notify_client_rejected", target=str(lead_id), detail="lead not found"
            )
            return {"ok": False, "errors": [f"lead {lead_id} not found"]}
        if not message:
            memory.log_action(
                conn, _ACTOR, "notify_client_rejected", target=str(lead_id), detail="empty message"
            )
            return {"ok": False, "errors": ["message is required"]}

        sent, detail = _send_telegram(message)
        status = "sent_telegram" if sent else "logged_stub"
        console_line = f"[notify_client:{status}] to={lead['email']} lead_id={lead_id} message={message!r}"
        try:
            print(console_line)
        except UnicodeEncodeError:
            # Some Windows consoles default to a non-UTF-8 codepage that can't
            # render emoji — degrade the console line only, never the message
            # actually sent to Telegram or stored in the audit log.
            print(console_line.encode("ascii", errors="backslashreplace").decode("ascii"))
        memory.log_action(conn, _ACTOR, "notify_client", target=str(lead_id), detail=f"{status}: {detail}")
        return {"ok": True, "status": status, "lead_id": lead_id, "message": message}
    finally:
        conn.close()


def search_knowledge(query: str) -> dict[str, Any]:
    """Search the AI Invention knowledge base (pricing, services, onboarding
    process, FAQ) and return the passages that answer a client's question.

    Use this whenever a lead asks about cost, what we offer, how long
    onboarding takes, support, refunds, or payment — answer from the returned
    chunks, never from memory.

    Args:
        query: the client's question, e.g. "how much does a chatbot cost?".

    Returns:
        Always {"ok": True, "query": str, "results": [{text, source, heading,
        score, backend}, ...], "count": int}. Retrieval degrades to a keyword
        index when no embedding key is configured, so this tool never fails
        the workflow — an empty results list just means nothing matched.
    """
    query = str(query or "").strip()
    results = rag.search_knowledge(query) if query else []
    conn = memory.init_db()
    try:
        memory.log_action(
            conn,
            _ACTOR,
            "search_knowledge",
            target=query[:120],
            detail=f"{len(results)} chunks"
            + (f" via {results[0]['backend']}" if results else ""),
        )
    finally:
        conn.close()
    return {"ok": True, "query": query, "results": results, "count": len(results)}
