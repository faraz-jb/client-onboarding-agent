import { NextResponse } from "next/server";
import { getProposals } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ proposals: getProposals() });
}
