"""SQLite persistence for the Client Onboarding Agent.

Local-only store: data/onboarding.db — gitignored, never committed, never
holds anything but this machine's own run data. Every tool that mutates
state also writes an agent_log row: this is the audit trail required by the
security-first rules in CLAUDE.md.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "onboarding.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    service TEXT NOT NULL,
    budget REAL,
    raw_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    overview TEXT NOT NULL,
    scope TEXT NOT NULL,
    timeline TEXT NOT NULL,
    pricing TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    steps_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a connection, creating the parent dir if needed. Caller closes it."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Create all tables if missing and return an open connection. Idempotent."""
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def log_action(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    target: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    """Write one audit-trail row. Called by every tool, success or rejection."""
    conn.execute(
        "INSERT INTO agent_log (actor, action, target, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (actor, action, target, detail, _now()),
    )
    conn.commit()


def insert_lead(
    conn: sqlite3.Connection,
    name: str,
    email: str,
    service: str,
    budget: Optional[float],
    raw: dict,
) -> int:
    cur = conn.execute(
        "INSERT INTO leads (name, email, service, budget, raw_json, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'new', ?)",
        (name, email, service, budget, json.dumps(raw), _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_lead(conn: sqlite3.Connection, lead_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row) if row else None


def insert_proposal(
    conn: sqlite3.Connection,
    lead_id: int,
    overview: str,
    scope: str,
    timeline: str,
    pricing: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO proposals (lead_id, overview, scope, timeline, pricing, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'draft', ?)",
        (lead_id, overview, scope, timeline, pricing, _now()),
    )
    conn.commit()
    return cur.lastrowid


def insert_delivery_plan(conn: sqlite3.Connection, lead_id: int, steps: list[dict[str, Any]]) -> int:
    cur = conn.execute(
        "INSERT INTO delivery_plans (lead_id, steps_json, status, created_at) "
        "VALUES (?, ?, 'planned', ?)",
        (lead_id, json.dumps(steps), _now()),
    )
    conn.commit()
    return cur.lastrowid
