"use client";

import { Suspense, useState, FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ShieldCheck, Loader2 } from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Only accept an internal path as the post-login destination — an
  // attacker-supplied absolute URL here would be an open redirect.
  const rawNext = searchParams.get("next");
  const next = rawNext && rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/dashboard";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    const data = new FormData(event.currentTarget);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: data.get("password") }),
      });
      const result = await res.json().catch(() => ({}));

      if (!res.ok || !result.ok) {
        setError((result.errors || ["login failed"]).join(", "));
        setSubmitting(false);
        return;
      }

      router.replace(next);
      router.refresh();
    } catch {
      setError("could not reach the server");
      setSubmitting(false);
    }
  }

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <label htmlFor="password">Admin password</label>
      <input
        id="password"
        name="password"
        type="password"
        autoComplete="current-password"
        placeholder="Enter admin password"
        required
        autoFocus
      />
      <button type="submit" className="btn btn-primary" disabled={submitting}>
        {submitting ? <Loader2 size={15} className="spin" /> : <ShieldCheck size={15} />}
        {submitting ? "Verifying…" : "Sign in"}
      </button>
      {error && <p className="form-msg error">{error}</p>}
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="nav-brand login-brand">
          <span className="dot" />
          Client Onboarding Agent
        </div>
        <h1>Admin sign-in</h1>
        <p className="login-sub">
          The dashboard exposes real client data and the agent trigger. Sign in to continue.
        </p>
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
        <Link href="/" className="login-back">
          ← Back to home
        </Link>
      </div>
    </div>
  );
}
