import { NextRequest, NextResponse } from "next/server";
import { clearSessionCookie } from "@/lib/auth";
import { clientIp } from "@/lib/rate-limit";
import { logAuthEvent } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Reaching this handler already implies a valid session — middleware protects
// the route, so an unauthenticated caller is turned away before it runs.
export async function POST(request: NextRequest) {
  const response = NextResponse.json({ ok: true });
  clearSessionCookie(response);
  logAuthEvent("auth_logout", clientIp(request.headers), null);
  return response;
}
