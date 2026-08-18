"use client";

import { useEffect, useRef, useState, useTransition, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { UserPlus, Loader2 } from "lucide-react";

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_ATTEMPTS = 40; // ~60s ceiling before giving up

const STATUS_LABEL: Record<string, string> = {
  new: "queued",
  processing: "processing…",
  classified: "classified…",
  proposal_ready: "proposal ready",
  error: "error",
};

interface LeadStatusResponse {
  leads: Array<{ id: number; status: string; priority: string | null }>;
}

export default function NewLeadForm() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [message, setMessage] = useState<{ type: "error" | "success"; text: string } | null>(null);
  const [trackedLeadId, setTrackedLeadId] = useState<number | null>(null);
  const [liveStatus, setLiveStatus] = useState<string | null>(null);
  const pollAttempts = useRef(0);

  useEffect(() => {
    if (trackedLeadId === null) return;

    pollAttempts.current = 0;
    const interval = setInterval(async () => {
      pollAttempts.current += 1;
      try {
        const res = await fetch("/api/leads", { cache: "no-store" });
        const data: LeadStatusResponse = await res.json();
        const lead = data.leads.find((l) => l.id === trackedLeadId);
        const status = lead?.status ?? null;
        setLiveStatus(status);

        const isTerminal = status === "proposal_ready" || status === "error";
        if (isTerminal || pollAttempts.current >= POLL_MAX_ATTEMPTS) {
          clearInterval(interval);
          setTrackedLeadId(null);
          startTransition(() => router.refresh());
        }
      } catch {
        // Transient fetch failure — keep polling until the attempt ceiling.
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trackedLeadId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setLiveStatus(null);

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

    setMessage({ type: "success", text: `Lead #${result.lead.id} added — starting agent…` });
    form.reset();
    startTransition(() => router.refresh());

    const leadId: number = result.lead.id;
    const processRes = await fetch("/api/agent/process-lead", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lead_id: leadId }),
    });

    if (!processRes.ok) {
      const processResult = await processRes.json().catch(() => ({}));
      setMessage({
        type: "error",
        text: (processResult.errors || ["failed to start the agent"]).join(", "),
      });
      return;
    }

    setLiveStatus("processing");
    setTrackedLeadId(leadId);
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
      {trackedLeadId !== null && liveStatus && (
        <p className="form-msg live-status">
          <Loader2 size={13} className="spin" />
          Lead #{trackedLeadId}: {STATUS_LABEL[liveStatus] ?? liveStatus}
        </p>
      )}
    </>
  );
}
