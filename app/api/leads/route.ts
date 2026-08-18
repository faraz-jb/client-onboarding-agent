import { NextRequest, NextResponse } from "next/server";
import { getLeads, insertLead } from "@/lib/db";
import { spawnAgentForLead } from "@/lib/run-agent";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ leads: getLeads() });
}

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, errors: ["request body must be JSON"] }, { status: 400 });
  }

  if (typeof body !== "object" || body === null) {
    return NextResponse.json({ ok: false, errors: ["request body must be a JSON object"] }, { status: 400 });
  }

  const { name, email, service, budget } = body as Record<string, unknown>;
  const result = insertLead({ name, email, service, budget });

  if (!result.ok) {
    return NextResponse.json(result, { status: 400 });
  }

  // Auto-process: classify -> proposal -> delivery -> notify (fire-and-forget).
  // Every lead source (receptionist webhook, website form) flows through here,
  // so a new lead is automatically classified and a proposal drafted.
  spawnAgentForLead(result.lead.id);

  return NextResponse.json(result, { status: 201 });
}
