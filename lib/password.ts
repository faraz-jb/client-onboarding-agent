// Password derivation — scrypt + timingSafeEqual. NODE RUNTIME ONLY.
//
// This module is deliberately separate from lib/auth.ts. middleware.ts imports
// lib/auth.ts for session verification and is bundled for the Edge runtime,
// where node:crypto does not exist — webpack resolves `node:` imports
// statically (even inside a dynamic import()), so any path from middleware to
// this file breaks the build. Keep it imported only from route handlers that
// pin `export const runtime = "nodejs"`.

import { scrypt, timingSafeEqual } from "node:crypto";

const SCRYPT_KEYLEN = 64;

/** Derive the scrypt hash of `password` with `salt`, as hex. */
export async function hashPassword(password: string, salt: string): Promise<string> {
  return new Promise((resolve, reject) => {
    scrypt(password, salt, SCRYPT_KEYLEN, (err, derivedKey) => {
      if (err) reject(err);
      else resolve(derivedKey.toString("hex"));
    });
  });
}

/**
 * Compare a candidate password against the expected hash in constant time.
 * Uses timingSafeEqual — never ===, which would leak the matching prefix
 * length through comparison timing.
 */
export async function verifyPassword(
  candidate: string,
  salt: string,
  expectedHash: string,
): Promise<boolean> {
  const candidateHash = await hashPassword(candidate, salt);
  const a = Buffer.from(candidateHash, "hex");
  const b = Buffer.from(expectedHash, "hex");

  // timingSafeEqual throws on length mismatch. Both sides are fixed-length
  // scrypt output, so unequal lengths mean a malformed expected hash rather
  // than a merely-wrong password.
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}
