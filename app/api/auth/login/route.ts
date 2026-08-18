import { NextRequest, NextResponse } from "next/server";
import { isAuthConfigured, setSessionCookie, signSession } from "@/lib/auth";
import { hashPassword, verifyPassword } from "@/lib/password";
import { checkRateLimit, clientIp } from "@/lib/rate-limit";
import { logAuthEvent } from "@/lib/db";

export const dynamic = "force-dynamic";
// Node runtime: scrypt + timingSafeEqual are node:crypto, not Edge APIs.
export const runtime = "nodejs";

const LOGIN_LIMIT = 5;
const LOGIN_WINDOW_MS = 60_000;

export async function POST(request: NextRequest) {
  const ip = clientIp(request.headers);

  // Rate limit before touching scrypt — an unthrottled login endpoint is both
  // a brute-force target and a CPU-exhaustion one, since each attempt costs a
  // full key derivation.
  const limit = checkRateLimit(`login:${ip}`, LOGIN_LIMIT, LOGIN_WINDOW_MS);
  if (!limit.allowed) {
    logAuthEvent("auth_login_rejected", ip, "rate limited");
    return NextResponse.json(
      { ok: false, errors: ["too many login attempts — try again shortly"] },
      { status: 429, headers: { "Retry-After": String(limit.retryAfterSeconds) } },
    );
  }

  if (!isAuthConfigured()) {
    logAuthEvent("auth_login_rejected", ip, "auth not configured");
    return NextResponse.json(
      { ok: false, errors: ["admin auth is not configured on this server"] },
      { status: 503 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, errors: ["request body must be JSON"] }, { status: 400 });
  }

  const password = (body as Record<string, unknown> | null)?.password;
  if (typeof password !== "string" || password.length === 0) {
    logAuthEvent("auth_login_rejected", ip, "missing password");
    return NextResponse.json({ ok: false, errors: ["password is required"] }, { status: 400 });
  }

  const salt = process.env.ADMIN_PASSWORD_SALT as string;
  const expectedHash = await hashPassword(process.env.ADMIN_PASSWORD as string, salt);
  const ok = await verifyPassword(password, salt, expectedHash);

  if (!ok) {
    logAuthEvent("auth_login_rejected", ip, "invalid password");
    return NextResponse.json({ ok: false, errors: ["invalid credentials"] }, { status: 401 });
  }

  const token = await signSession("admin");
  if (!token) {
    logAuthEvent("auth_login_rejected", ip, "session signing unavailable");
    return NextResponse.json({ ok: false, errors: ["session could not be issued"] }, { status: 503 });
  }

  const response = NextResponse.json({ ok: true });
  setSessionCookie(response, token);
  logAuthEvent("auth_login", ip, null);
  return response;
}
