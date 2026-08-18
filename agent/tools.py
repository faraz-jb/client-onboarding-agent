"""ADK tools for the Client Onboarding Agent.

Plain, type-hinted functions — wrapped in google.adk.tools.FunctionTool at
registration time in agent.py. Kept as plain functions here too so they can
be called directly (no LLM, no network) for local dry-run and test paths.

Every tool validates its own input and writes an agent_log audit row via
memory.py — security-first rule from CLAUDE.md: no unaudited state changes.
"""

import re
from typing import Any, Optional

from . import memory

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ACTOR = "client_onboarding_agent"


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


def notify_client(lead_id: int, message: str) -> dict[str, Any]:
    """Notify the client. Phase 1 stub: logs to console + audit trail only.

    Phase 3 will replace the console log with a real email/SMS send.

    Args:
        lead_id: id of the lead to notify.
        message: message body to send.

    Returns:
        On success: {"ok": True, "status": "logged_stub", "lead_id": int, "message": str}.
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

        print(f"[notify_client stub] to={lead['email']} lead_id={lead_id} message={message!r}")
        memory.log_action(conn, _ACTOR, "notify_client", target=str(lead_id), detail=message)
        return {"ok": True, "status": "logged_stub", "lead_id": lead_id, "message": message}
    finally:
        conn.close()
