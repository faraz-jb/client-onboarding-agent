import { NextRequest, NextResponse } from "next/server";
import { markLeadProcessing } from "@/lib/db";
import { spawnAgentForLead } from "@/lib/run-agent";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Fire-and-forget: this route triggers the Python agent as a subprocess and
// returns as soon as it's spawned. The agent itself moves leads.status
// through processing -> classified -> proposal_ready as it works, so the
// client tracks progress by polling GET /api/leads (see NewLeadForm.tsx).
export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, errors: ["request body must be JSON"] }, { status: 400 });
  }

  const leadId = Number((body as Record<string, unknown> | null)?.lead_id);
  if (!Number.isInteger(leadId) || leadId <= 0) {
    return NextResponse.json({ ok: false, errors: ["lead_id must be a positive integer"] }, { status: 400 });
  }

  const marked = markLeadProcessing(leadId);
  if (!marked.ok) {
    return NextResponse.json(marked, { status: 404 });
  }

  const spawned = spawnAgentForLead(leadId);
  if (!spawned) {
    return NextResponse.json(
      { ok: false, errors: ["Python venv not found — run: python -m venv .venv"] },
      { status: 500 },
    );
  }

  return NextResponse.json({ ok: true, lead_id: leadId, status: "processing" }, { status: 202 });
}
