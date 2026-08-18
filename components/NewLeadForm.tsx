"use client";

import { useState, useTransition, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { UserPlus } from "lucide-react";

export default function NewLeadForm() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [message, setMessage] = useState<{ type: "error" | "success"; text: string } | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);

    const form = event.currentTarget;
    const data = new FormData(form);
    const payload = {
      name: data.get("name"),
      email: data.get("email"),
      service: data.get("service"),
      budget: data.get("budget") || undefined,
    };

    const res = await fetch("/api/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await res.json();

    if (!res.ok || !result.ok) {
      setMessage({ type: "error", text: (result.errors || ["failed to create lead"]).join(", ") });
      return;
    }

    setMessage({ type: "success", text: `Lead #${result.lead.id} added.` });
    form.reset();
    startTransition(() => router.refresh());
  }

  return (
    <>
      <form className="lead-form" onSubmit={handleSubmit}>
        <input name="name" placeholder="Client name" required />
        <input name="email" type="email" placeholder="Email" required />
        <input name="service" placeholder="Service (optional)" />
        <input name="budget" type="number" min="0" step="0.01" placeholder="Budget (optional)" />
        <button type="submit" className="btn btn-primary" disabled={isPending}>
          <UserPlus size={15} />
          {isPending ? "Adding…" : "Add lead"}
        </button>
      </form>
      {message && <p className={`form-msg ${message.type}`}>{message.text}</p>}
    </>
  );
}
