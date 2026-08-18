// Route protection — the single gate in front of every non-public surface.
//
// Runs on the Edge runtime, so it validates sessions with Web Crypto only
// (see the runtime-split note in lib/auth.ts). Anything not matched by
// `config.matcher` below never reaches this file.
//
// PUBLIC:    / (landing), /login, POST /api/auth/login, POST /api/leads
// PROTECTED: /dashboard, GET /api/leads, /api/proposals, /api/delivery,
//            /api/audit, /api/agent/*, POST /api/auth/logout

import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, verifySession } from "@/lib/auth";
import { checkRateLimit, clientIp } from "@/lib/rate-limit";

const LEADS_INTAKE_LIMIT = 10;
const LEADS_INTAKE_WINDOW_MS = 60_000;

function isPublic(pathname: string, method: string): boolean {
  // Lead intake stays open — that is the whole point of a public intake form.
  // Reading leads back does not.
  if (pathname === "/api/leads" && method === "POST") return true;
  return false;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const method = request.method;

  if (isPublic(pathname, method)) {
    // Public but abusable: throttle per IP so the intake form cannot be used
    // to flood the DB (and, downstream, the agent) with junk leads.
    const ip = clientIp(request.headers);
    const limit = checkRateLimit(`leads:${ip}`, LEADS_INTAKE_LIMIT, LEADS_INTAKE_WINDOW_MS);
    if (!limit.allowed) {
      return NextResponse.json(
        { ok: false, errors: ["too many submissions — try again shortly"] },
        { status: 429, headers: { "Retry-After": String(limit.retryAfterSeconds) } },
      );
    }
    return NextResponse.next();
  }

  const session = await verifySession(request.cookies.get(SESSION_COOKIE)?.value);
  if (session) return NextResponse.next();

  // Unauthenticated. APIs get a JSON 401 so fetch callers can react; page
  // requests get bounced to the login screen with a return path.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ ok: false, errors: ["authentication required"] }, { status: 401 });
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/api/leads",
    "/api/proposals",
    "/api/delivery",
    "/api/audit",
    "/api/agent/:path*",
    "/api/auth/logout",
  ],
};
