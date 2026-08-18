// SQLite data access — read/write via node:sqlite (Node 22+), no ORM.
// Same schema/audit-trail contract as agent/memory.py: every mutation here
// also writes an agent_log row (security-first rule from CLAUDE.md).

import { DatabaseSync } from "node:sqlite";
import path from "node:path";

const DB_PATH = process.env.DB_PATH || path.join(process.cwd(), "data", "onboarding.db");

const SCHEMA = `
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
`;

let migrated = false;

// Mirrors agent/memory.py's additive migration: leads.priority is set by the
// classify_lead_agent sub-agent (Phase 3 wiring), added here so the schema
// stays in sync whichever side (Python agent or this UI) touches the DB first.
function migrate(conn: DatabaseSync): void {
  if (migrated) return;
  const cols = conn.prepare("PRAGMA table_info(leads)").all() as Array<{ name: string }>;
  if (!cols.some((c) => c.name === "priority")) {
    conn.exec("ALTER TABLE leads ADD COLUMN priority TEXT");
  }
  migrated = true;
}

function open(): DatabaseSync {
  const conn = new DatabaseSync(DB_PATH);
  conn.exec(SCHEMA);
  migrate(conn);
  return conn;
}

function nowIso(): string {
  return new Date().toISOString();
}

function logAction(
  conn: DatabaseSync,
  actor: string,
  action: string,
  target: string | null,
  detail: string | null,
): void {
  conn
    .prepare(
      "INSERT INTO agent_log (actor, action, target, detail, created_at) VALUES (?, ?, ?, ?, ?)",
    )
    .run(actor, action, target, detail, nowIso());
}

export interface Lead {
  id: number;
  name: string;
  email: string;
  service: string;
  budget: number | null;
  priority: string | null;
  status: string;
  created_at: string;
}

export interface Proposal {
  id: number;
  lead_id: number;
  lead_name: string | null;
  overview: string;
  scope: string;
  timeline: string;
  pricing: string;
  status: string;
  created_at: string;
}

export interface DeliveryStep {
  step: string;
  description: string;
  status: string;
}

export interface DeliveryPlan {
  id: number;
  lead_id: number;
  lead_name: string | null;
  steps: DeliveryStep[];
  status: string;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  actor: string;
  action: string;
  target: string | null;
  detail: string | null;
  result: "ok" | "rejected";
  created_at: string;
}

export function getLeads(): Lead[] {
  const conn = open();
  try {
    return conn
      .prepare("SELECT id, name, email, service, budget, priority, status, created_at FROM leads ORDER BY created_at DESC")
      .all() as unknown as Lead[];
  } finally {
    conn.close();
  }
}

export function getProposals(): Proposal[] {
  const conn = open();
  try {
    return conn
      .prepare(
        `SELECT p.id, p.lead_id, l.name AS lead_name, p.overview, p.scope, p.timeline,
                p.pricing, p.status, p.created_at
         FROM proposals p LEFT JOIN leads l ON l.id = p.lead_id
         ORDER BY p.created_at DESC`,
      )
      .all() as unknown as Proposal[];
  } finally {
    conn.close();
  }
}

export function getDeliveryPlans(): DeliveryPlan[] {
  const conn = open();
  try {
    const rows = conn
      .prepare(
        `SELECT dp.id, dp.lead_id, l.name AS lead_name, dp.steps_json, dp.status, dp.created_at
         FROM delivery_plans dp LEFT JOIN leads l ON l.id = dp.lead_id
         ORDER BY dp.created_at DESC`,
      )
      .all() as unknown as Array<{
      id: number;
      lead_id: number;
      lead_name: string | null;
      steps_json: string;
      status: string;
      created_at: string;
    }>;
    return rows.map((row) => ({
      id: row.id,
      lead_id: row.lead_id,
      lead_name: row.lead_name,
      steps: JSON.parse(row.steps_json) as DeliveryStep[],
      status: row.status,
      created_at: row.created_at,
    }));
  } finally {
    conn.close();
  }
}

export function getAuditLog(): AuditEntry[] {
  const conn = open();
  try {
    const rows = conn
      .prepare("SELECT id, actor, action, target, detail, created_at FROM agent_log ORDER BY created_at DESC LIMIT 200")
      .all() as unknown as Array<Omit<AuditEntry, "result">>;
    return rows.map((row) => ({
      ...row,
      result: row.action.endsWith("_rejected") ? "rejected" : "ok",
    }));
  } finally {
    conn.close();
  }
}

export interface NewLeadInput {
  name: unknown;
  email: unknown;
  service: unknown;
  budget: unknown;
}

export interface InsertLeadResult {
  ok: true;
  lead: Lead;
}

export interface InsertLeadError {
  ok: false;
  errors: string[];
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function insertLead(input: NewLeadInput): InsertLeadResult | InsertLeadError {
  const errors: string[] = [];

  const name = String(input.name ?? "").trim();
  const email = String(input.email ?? "").trim().toLowerCase();
  const service = String(input.service ?? "").trim() || "unspecified";

  let budget: number | null = null;
  if (input.budget !== undefined && input.budget !== null && input.budget !== "") {
    const parsed = Number(input.budget);
    if (Number.isNaN(parsed)) {
      errors.push("budget must be numeric");
    } else if (parsed < 0) {
      errors.push("budget must be >= 0");
    } else {
      budget = parsed;
    }
  }

  if (!name) errors.push("name is required");
  if (!email || !EMAIL_RE.test(email)) errors.push("a valid email is required");

  const conn = open();
  try {
    if (errors.length > 0) {
      logAction(conn, "dashboard_api", "intake_lead_rejected", email || name || null, errors.join("; "));
      return { ok: false, errors };
    }

    const rawJson = JSON.stringify({ name, email, service, budget });
    const createdAt = nowIso();
    const result = conn
      .prepare(
        "INSERT INTO leads (name, email, service, budget, raw_json, status, created_at) VALUES (?, ?, ?, ?, ?, 'new', ?)",
      )
      .run(name, email, service, budget, rawJson, createdAt);

    const leadId = Number(result.lastInsertRowid);
    logAction(conn, "dashboard_api", "intake_lead", String(leadId), null);

    return {
      ok: true,
      lead: { id: leadId, name, email, service, budget, priority: null, status: "new", created_at: createdAt },
    };
  } finally {
    conn.close();
  }
}
