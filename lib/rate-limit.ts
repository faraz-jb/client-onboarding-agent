// In-memory fixed-window rate limiter — no external dependency.
//
// Scope note: state lives in the module closure, so each runtime/process keeps
// its own counters (Edge middleware and Node route handlers do not share a
// store, and a multi-instance deploy would count per instance). That is the
// accepted trade-off for a zero-dependency limiter: it blunts brute-force and
// cost-abuse from a single client, it is not a distributed quota.

interface Window {
  count: number;
  resetAt: number;
}

const windows = new Map<string, Window>();

// Bound the map so a flood of unique keys (spoofed IPs) cannot grow it without
// limit. Entries are cheap; we sweep expired ones whenever we cross the mark.
const MAX_TRACKED_KEYS = 10_000;

function sweep(now: number): void {
  for (const [key, window] of windows) {
    if (window.resetAt <= now) windows.delete(key);
  }
}

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  retryAfterSeconds: number;
}

/**
 * Count one hit against `key` and report whether it is within `limit` per
 * `windowMs`. Callers that decide to reject should return 429 and surface
 * `retryAfterSeconds` in a Retry-After header.
 */
export function checkRateLimit(key: string, limit: number, windowMs: number): RateLimitResult {
  const now = Date.now();

  if (windows.size >= MAX_TRACKED_KEYS) sweep(now);

  const existing = windows.get(key);
  if (!existing || existing.resetAt <= now) {
    windows.set(key, { count: 1, resetAt: now + windowMs });
    return { allowed: true, remaining: limit - 1, retryAfterSeconds: 0 };
  }

  existing.count += 1;
  const retryAfterSeconds = Math.max(1, Math.ceil((existing.resetAt - now) / 1000));

  if (existing.count > limit) {
    return { allowed: false, remaining: 0, retryAfterSeconds };
  }
  return { allowed: true, remaining: limit - existing.count, retryAfterSeconds };
}

/**
 * Best-effort client IP for rate-limit keying. Behind a proxy the left-most
 * x-forwarded-for entry is the client; with no proxy header we fall back to a
 * shared bucket rather than failing open per-request.
 */
export function clientIp(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  return headers.get("x-real-ip")?.trim() || "unknown";
}
