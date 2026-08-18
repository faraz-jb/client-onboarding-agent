// Admin authentication — scrypt password derivation + HMAC-SHA256 sessions.
//
// RUNTIME SPLIT (deliberate, do not collapse):
//   - This file is EDGE-SAFE. Session sign/verify use Web Crypto
//     (crypto.subtle), which exists in both the Edge runtime (middleware.ts)
//     and the Node runtime, so middleware can validate a session without
//     pulling a Node-only module into the Edge bundle.
//   - Password hashing (scrypt + timingSafeEqual) lives in lib/password.ts and
//     is imported ONLY by POST /api/auth/login, which pins runtime = "nodejs".
//     It must never be imported from here: webpack resolves `node:` schemes
//     statically, so a single path from middleware to node:crypto fails the
//     Edge build outright.
//
// No credential is ever stored in the database: the expected hash is derived
// on demand from ADMIN_PASSWORD + ADMIN_PASSWORD_SALT in the environment.

import type { NextResponse } from "next/server";

export const SESSION_COOKIE = "coa_session";

const SESSION_TTL_SECONDS = 24 * 60 * 60; // 24h

export interface SessionPayload {
  sub: string;
  iat: number;
  exp: number;
}

// --- base64url helpers (available in both runtimes) ---

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// Backed by an explicit ArrayBuffer so the result satisfies BufferSource —
// a bare `new Uint8Array(n)` is typed Uint8Array<ArrayBufferLike>, which
// crypto.subtle's signature rejects under strict TypeScript.
function fromBase64Url(value: string): Uint8Array<ArrayBuffer> {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// --- Session: HMAC-SHA256 via Web Crypto (Edge + Node) ---

async function sessionKey(): Promise<CryptoKey | null> {
  const secret = process.env.SESSION_SECRET;
  // Fail closed: with no secret configured nothing can be signed or verified,
  // so every protected route denies rather than silently trusting cookies.
  if (!secret) return null;

  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

/** Issue a signed session token for `subject`. Returns null if unconfigured. */
export async function signSession(subject: string): Promise<string | null> {
  const key = await sessionKey();
  if (!key) return null;

  const issuedAt = Math.floor(Date.now() / 1000);
  const payload: SessionPayload = {
    sub: subject,
    iat: issuedAt,
    exp: issuedAt + SESSION_TTL_SECONDS,
  };

  const body = toBase64Url(new TextEncoder().encode(JSON.stringify(payload)));
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  return `${body}.${toBase64Url(new Uint8Array(signature))}`;
}

/**
 * Validate a session token: signature first (crypto.subtle.verify is
 * constant-time), then expiry. Returns the payload, or null for any of
 * unconfigured / malformed / bad signature / expired.
 */
export async function verifySession(token: string | undefined | null): Promise<SessionPayload | null> {
  if (!token) return null;

  const key = await sessionKey();
  if (!key) return null;

  const parts = token.split(".");
  if (parts.length !== 2) return null;
  const [body, signature] = parts;

  let valid: boolean;
  try {
    valid = await crypto.subtle.verify(
      "HMAC",
      key,
      fromBase64Url(signature),
      new TextEncoder().encode(body),
    );
  } catch {
    return null; // malformed base64url in the signature segment
  }
  if (!valid) return null;

  let payload: SessionPayload;
  try {
    payload = JSON.parse(new TextDecoder().decode(fromBase64Url(body))) as SessionPayload;
  } catch {
    return null;
  }

  if (typeof payload?.exp !== "number" || payload.exp <= Math.floor(Date.now() / 1000)) {
    return null;
  }
  return payload;
}

/** True when all three auth env vars are present — routes fail closed otherwise. */
export function isAuthConfigured(): boolean {
  return Boolean(
    process.env.ADMIN_PASSWORD && process.env.ADMIN_PASSWORD_SALT && process.env.SESSION_SECRET,
  );
}

// --- Cookie helpers ---

export function setSessionCookie(response: NextResponse, token: string): void {
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
}

export function clearSessionCookie(response: NextResponse): void {
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}
