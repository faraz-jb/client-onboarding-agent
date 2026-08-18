"""Local test suite for Phase 1 — no Gemini API key required.

Exercises tools.py directly (no LLM), the DB schema, and the agent
structure via agent.build_agent()/run_dry(). Run with:
    python -m agent.test_agent
or:
    python agent/test_agent.py

Prints "PASS" and exits 0 on success, "FAIL" with a traceback and exits 1
otherwise.
"""

import os
import sys
import traceback
from pathlib import Path

if __package__ in (None, ""):
    # Allow `python agent/test_agent.py` in addition to `python -m agent.test_agent`.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from agent import agent as agent_module
    from agent import memory
    from agent.tools import (
        create_delivery_plan,
        draft_proposal,
        finalize_proposal,
        intake_lead,
        notify_client,
        update_lead_priority,
    )
else:
    from . import agent as agent_module
    from . import memory
    from .tools import (
        create_delivery_plan,
        draft_proposal,
        finalize_proposal,
        intake_lead,
        notify_client,
        update_lead_priority,
    )

EXPECTED_TABLES = {"leads", "proposals", "delivery_plans", "agent_log"}


def test_db_schema() -> None:
    conn = memory.init_db()
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row["name"] for row in rows}
        missing = EXPECTED_TABLES - table_names
        assert not missing, f"missing tables: {missing}"
    finally:
        conn.close()


def test_intake_lead_valid() -> int:
    result = intake_lead(
        {
            "name": "test_Client Alpha",
            "email": "test_alpha@example.com",
            "service": "AI Website",
            "budget": 5000,
        }
    )
    assert result["ok"] is True, result
    assert isinstance(result["lead_id"], int)
    assert result["lead"]["email"] == "test_alpha@example.com"
    return result["lead_id"]


def test_intake_lead_invalid() -> None:
    result = intake_lead({"name": "", "email": "not-an-email"})
    assert result["ok"] is False, result
    assert "name is required" in result["errors"]
    assert any("email" in e for e in result["errors"])


def test_intake_lead_bad_budget() -> None:
    result = intake_lead({"name": "test_Bad Budget", "email": "test_bad@example.com", "budget": "abc"})
    assert result["ok"] is False, result
    assert any("budget" in e for e in result["errors"])


def test_draft_proposal(lead_id: int) -> None:
    result = draft_proposal(lead_id)
    assert result["ok"] is True, result
    proposal = result["proposal"]
    for section in ("overview", "scope", "timeline", "pricing"):
        assert section in proposal and proposal[section], f"missing section: {section}"


def test_draft_proposal_missing_lead() -> None:
    result = draft_proposal(999_999_999)
    assert result["ok"] is False, result


def test_create_delivery_plan(lead_id: int) -> None:
    result = create_delivery_plan(lead_id)
    assert result["ok"] is True, result
    steps = result["steps"]
    assert [s["step"] for s in steps] == ["discovery", "build", "review", "handover"], steps


def test_notify_client(lead_id: int) -> None:
    result = notify_client(lead_id, "test_ Welcome, we received your request.")
    assert result["ok"] is True, result
    assert result["status"] == "logged_stub"


def test_notify_client_empty_message(lead_id: int) -> None:
    result = notify_client(lead_id, "   ")
    assert result["ok"] is False, result


def test_update_lead_priority(lead_id: int) -> None:
    result = update_lead_priority(lead_id, "HOT")
    assert result["ok"] is True, result
    assert result["priority"] == "hot"

    conn = memory.init_db()
    try:
        lead = memory.get_lead(conn, lead_id)
    finally:
        conn.close()
    assert lead["priority"] == "hot"


def test_update_lead_priority_invalid(lead_id: int) -> None:
    result = update_lead_priority(lead_id, "urgent")
    assert result["ok"] is False, result


def test_finalize_proposal(lead_id: int) -> None:
    proposal = draft_proposal(lead_id)
    assert proposal["ok"] is True, proposal
    result = finalize_proposal(
        proposal["proposal_id"],
        overview="test_ final overview",
        scope="test_ final scope",
        timeline="test_ final timeline",
        pricing="test_ final pricing",
    )
    assert result["ok"] is True, result


def test_finalize_proposal_missing() -> None:
    result = finalize_proposal(999_999_999, overview="x", scope="x", timeline="x", pricing="x")
    assert result["ok"] is False, result


def test_agent_structure_without_api_key() -> None:
    saved_key = os.environ.pop("GEMINI_API_KEY", None)
    try:
        agent = agent_module.build_agent()
        assert agent.name == "client_onboarding_agent"
        assert len(agent.tools) == 6
        assert len(agent.sub_agents) == 2
        assert {sa.name for sa in agent.sub_agents} == {"classify_lead_agent", "extract_info_agent"}
    finally:
        if saved_key is not None:
            os.environ["GEMINI_API_KEY"] = saved_key


def test_run_dry() -> None:
    saved_key = os.environ.pop("GEMINI_API_KEY", None)
    try:
        result = agent_module.run_dry(
            '{"name": "test_Dry Run Client", "email": "test_dryrun@example.com", "service": "AI Chatbot"}'
        )
        assert result["tool_count"] == 6
        assert result["sub_agent_count"] == 2
        assert result["intake_result"]["ok"] is True
    finally:
        if saved_key is not None:
            os.environ["GEMINI_API_KEY"] = saved_key


def test_process_lead_offline() -> None:
    """No GEMINI_API_KEY in this test process, so process_lead runs the offline path."""
    saved_key = os.environ.pop("GEMINI_API_KEY", None)
    try:
        intake = intake_lead(
            {
                "name": "test_Process Lead Client",
                "email": "test_processlead@example.com",
                "service": "AI Website",
                "budget": 8000,
            }
        )
        assert intake["ok"] is True, intake
        lead_id = intake["lead_id"]

        result = agent_module.process_lead(lead_id)
        assert result["ok"] is True, result
        assert result["mode"] == "offline"
        assert result["priority"] == "hot"  # budget >= 3000 and a real service -> hot heuristic
        assert result["proposal_source"] == "skeleton"
        assert isinstance(result["proposal_id"], int)
        assert isinstance(result["delivery_plan_id"], int)
        assert result["notify"]["ok"] is True
        assert result["notify"]["status"] == "logged_stub"  # no Telegram credentials in test env

        conn = memory.init_db()
        try:
            lead = memory.get_lead(conn, lead_id)
            assert lead["status"] == "proposal_ready"
            assert lead["priority"] == "hot"
        finally:
            conn.close()
    finally:
        if saved_key is not None:
            os.environ["GEMINI_API_KEY"] = saved_key


def test_process_lead_missing() -> None:
    result = agent_module.process_lead(999_999_999)
    assert result["ok"] is False, result


def test_audit_log_has_entries() -> None:
    conn = memory.init_db()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM agent_log").fetchone()["c"]
        assert count > 0, "agent_log should have audit rows after the tests above"
    finally:
        conn.close()


def run_all() -> None:
    test_db_schema()
    lead_id = test_intake_lead_valid()
    test_intake_lead_invalid()
    test_intake_lead_bad_budget()
    test_draft_proposal(lead_id)
    test_draft_proposal_missing_lead()
    test_create_delivery_plan(lead_id)
    test_notify_client(lead_id)
    test_notify_client_empty_message(lead_id)
    test_update_lead_priority(lead_id)
    test_update_lead_priority_invalid(lead_id)
    test_finalize_proposal(lead_id)
    test_finalize_proposal_missing()
    test_agent_structure_without_api_key()
    test_run_dry()
    test_process_lead_offline()
    test_process_lead_missing()
    test_audit_log_has_entries()


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
