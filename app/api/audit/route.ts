import { NextResponse } from "next/server";
import { getAuditLog } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ audit_log: getAuditLog() });
}
