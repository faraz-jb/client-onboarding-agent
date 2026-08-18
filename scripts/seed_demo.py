"""Seed the dashboard with demo leads for the hackathon walkthrough.

Runs the same offline path as `python -m agent.agent --lead-id <id> --dry-run`:
every step goes through the real tools in agent/tools.py, so the rows this
writes are structurally identical to what the agent produces in a live run.
Nothing here calls Gemini and nothing sends a Telegram message.

Usage:
    python scripts/seed_demo.py

The database it writes (data/onboarding.db) is gitignored and never committed.
Each run appends a fresh set of leads rather than replacing the previous one.
"""

import sys
from pathlib import Path

# Allow `python scripts/seed_demo.py` from anywhere — the agent package lives
# one level up from this file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import memory  # noqa: E402
from agent.agent import _classify_lead_offline  # noqa: E402  (same heuristic the agent uses)
from agent.tools import (  # noqa: E402
    create_delivery_plan,
    draft_proposal,
    finalize_proposal,
    intake_lead,
    notify_client,
    update_lead_priority,
)

# How far each demo lead should progress. The real pipeline takes every lead
# all the way to proposal_ready, but a dashboard where all five rows look
# identical demos nothing — the classify-only leads stop at a genuine
# intermediate state the pipeline actually passes through.
STAGE_CLASSIFY = "classify"    # -> status classified
STAGE_FULL = "full"            # -> status proposal_ready

# Budgets drive the classifier: >= 3000 with a named service is hot, any
# positive budget is warm, and a lead with no stated budget is cold. The two
# cold leads below therefore carry no budget — an enquiry with no number
# attached is precisely what "cold" means to the heuristic.
DEMO_LEADS = [
    {
        "lead": {
            "name": "Aisha Rahman",
            "email": "aisha.rahman@example.com",
            "service": "AI Website",
            "budget": 8500,
        },
        "stage": STAGE_FULL,
        "proposal": {
            "overview": (
                "Aisha's team needs a premium marketing site that converts inbound "
                "traffic without a manual follow-up step. We propose a Next.js build "
                "with an embedded AI assistant that qualifies visitors and routes "
                "them straight into the onboarding pipeline."
            ),
            "scope": (
                "Five-page responsive site (home, services, case studies, pricing, "
                "contact), CMS-backed blog, embedded AI chat assistant trained on the "
                "service catalogue, lead capture wired to the onboarding agent, and "
                "analytics instrumentation."
            ),
            "timeline": (
                "Discovery week 1. Design and content structure weeks 2-3. Build and "
                "assistant training weeks 4-6. Client review week 7. Handover week 8."
            ),
            "pricing": (
                "USD 8,500 fixed fee against the stated budget: 40% at kickoff, 40% at "
                "review, 20% on handover. Hosting and model usage billed at cost."
            ),
        },
    },
    {
        "lead": {
            "name": "Daniel Okafor",
            "email": "daniel.okafor@example.com",
            "service": "WhatsApp Automation",
            "budget": 2400,
        },
        "stage": STAGE_FULL,
        "proposal": {
            "overview": (
                "Daniel's storefront handles order enquiries manually over WhatsApp. "
                "We propose an automation layer that answers routine questions, "
                "captures order details, and escalates only what needs a human."
            ),
            "scope": (
                "WhatsApp Business API onboarding, intent routing for the top enquiry "
                "categories, order-detail capture into the existing sheet, human "
                "handoff rules, and a two-week supervised tuning window after launch."
            ),
            "timeline": (
                "Discovery week 1. Flow design and API onboarding week 2. Build and "
                "integration weeks 3-4. Supervised tuning week 5. Handover week 6."
            ),
            "pricing": (
                "USD 2,400 against the stated budget: 50% at kickoff, 50% on handover. "
                "WhatsApp API message fees are billed by the provider directly."
            ),
        },
    },
    {
        "lead": {
            "name": "Mei Ling Tan",
            "email": "meiling.tan@example.com",
            "service": "SEO Content System",
            "budget": 1800,
        },
        # Classified and waiting on a scoping call before anything is drafted.
        "stage": STAGE_CLASSIFY,
    },
    {
        "lead": {
            "name": "Rafael Moreno",
            "email": "rafael.moreno@example.com",
            "service": "Receptionist Agent",
            # No budget stated — the enquiry came in without one.
        },
        "stage": STAGE_CLASSIFY,
    },
    {
        "lead": {
            "name": "Priya Nair",
            "email": "priya.nair@example.com",
            "service": "CRM Integration",
            # No budget stated — cold, same as Rafael above.
        },
        "stage": STAGE_CLASSIFY,
    },
]


def _set_status(lead_id: int, status: str) -> None:
    conn = memory.init_db()
    try:
        memory.update_lead_status(conn, lead_id, status)
    finally:
        conn.close()


def _fetch(lead_id: int) -> dict:
    conn = memory.init_db()
    try:
        return memory.get_lead(conn, lead_id) or {}
    finally:
        conn.close()


def seed_one(spec: dict) -> dict:
    """Run one demo lead through the pipeline as far as its stage allows."""
    intake = intake_lead(spec["lead"])
    if not intake["ok"]:
        raise RuntimeError(f"intake failed for {spec['lead']['name']}: {intake['errors']}")
    lead_id = intake["lead_id"]

    # Classify with the same offline heuristic the agent falls back to, then
    # persist through the real tool so the audit trail matches a live run.
    stored = _fetch(lead_id)
    priority = _classify_lead_offline(stored)
    result = update_lead_priority(lead_id, priority)
    if not result["ok"]:
        raise RuntimeError(f"classify failed for {lead_id}: {result['errors']}")
    _set_status(lead_id, "classified")

    if spec["stage"] == STAGE_CLASSIFY:
        return _fetch(lead_id)

    # Full pipeline: proposal skeleton -> final copy -> delivery plan -> notify.
    drafted = draft_proposal(lead_id)
    if not drafted["ok"]:
        raise RuntimeError(f"draft_proposal failed for {lead_id}: {drafted['errors']}")

    finalized = finalize_proposal(drafted["proposal_id"], **spec["proposal"])
    if not finalized["ok"]:
        raise RuntimeError(f"finalize_proposal failed for {lead_id}: {finalized['errors']}")
    _set_status(lead_id, "proposal_ready")

    plan = create_delivery_plan(lead_id)
    if not plan["ok"]:
        raise RuntimeError(f"create_delivery_plan failed for {lead_id}: {plan['errors']}")

    budget = stored.get("budget")
    budget_display = f"${budget:,.0f}" if budget is not None else "budget TBD"
    notify_client(
        lead_id,
        f"New lead: {stored['name']} ({stored['service']}, {budget_display}) — priority: {priority}",
    )

    return _fetch(lead_id)


def main() -> None:
    memory.init_db().close()

    seeded = [seed_one(spec) for spec in DEMO_LEADS]

    header = f"{'ID':>4}  {'NAME':<16}  {'SERVICE':<22}  {'PRIORITY':<12}  STATUS"
    print()
    print(header)
    print("-" * len(header))
    for lead in seeded:
        print(
            f"{lead['id']:>4}  {lead['name']:<16}  {lead['service']:<22}  "
            f"{lead['priority'] or 'unclassified':<12}  {lead['status']}"
        )
    print()
    print(f"Seeded {len(seeded)} demo leads into {memory.DEFAULT_DB_PATH}")


if __name__ == "__main__":
    main()
