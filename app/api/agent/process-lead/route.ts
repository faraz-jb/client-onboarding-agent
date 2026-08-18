import { NextRequest, NextResponse } from "next/server";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { markLeadProcessing } from "@/lib/db";

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

  const projectRoot = process.cwd();
  const pythonPath =
    process.platform === "win32"
      ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
      : path.join(projectRoot, ".venv", "bin", "python");

  if (!existsSync(pythonPath)) {
    return NextResponse.json(
      { ok: false, errors: [`Python venv not found at ${pythonPath} — run: python -m venv .venv`] },
      { status: 500 },
    );
  }

  const child = spawn(pythonPath, ["-m", "agent.agent", "--lead-id", String(leadId)], {
    cwd: projectRoot,
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stdout.on("data", (chunk: Buffer) => {
    console.log(`[process-lead:${leadId}]`, chunk.toString().trim());
  });
  child.stderr.on("data", (chunk: Buffer) => {
    console.error(`[process-lead:${leadId}]`, chunk.toString().trim());
  });
  child.on("error", (err) => {
    console.error(`[process-lead:${leadId}] failed to spawn`, err);
  });

  return NextResponse.json({ ok: true, lead_id: leadId, status: "processing" }, { status: 202 });
}
