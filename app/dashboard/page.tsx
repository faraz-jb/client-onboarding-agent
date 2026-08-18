import Link from "next/link";
import { Users, FileText, Rocket, ShieldCheck, Inbox } from "lucide-react";
import { getLeads, getProposals, getDeliveryPlans, getAuditLog } from "@/lib/db";
import { formatBudget, formatDate, priorityPillClass } from "@/lib/format";
import NewLeadForm from "@/components/NewLeadForm";

export const dynamic = "force-dynamic";

const DELIVERY_STEP_ORDER = ["discovery", "build", "review", "handover"];

function EmptyState({ label }: { label: string }) {
  return (
    <div className="empty-state">
      <Inbox size={26} />
      <p>{label}</p>
    </div>
  );
}

export default function DashboardPage() {
  const leads = getLeads();
  const proposals = getProposals();
  const deliveryPlans = getDeliveryPlans();
  const auditLog = getAuditLog();

  return (
    <div className="shell">
      <nav className="nav">
        <div className="nav-brand">
          <span className="dot" />
          Client Onboarding Agent
        </div>
        <div className="nav-links">
          <Link href="/">Home</Link>
        </div>
      </nav>

      <div className="page-header">
        <h1>Dashboard</h1>
        <p>Live state from the agent&apos;s SQLite store — nothing here is simulated.</p>
      </div>

      <div className="dashboard-grid">
        {/* Leads */}
        <section className="card">
          <div className="card-header">
            <div className="card-header-title">
              <Users />
              Leads
            </div>
            <span className="card-count">{leads.length}</span>
          </div>
          <NewLeadForm />
          {leads.length === 0 ? (
            <EmptyState label="No leads yet — agent is waiting" />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Service</th>
                    <th>Budget</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((lead) => (
                    <tr key={lead.id}>
                      <td>{lead.name}</td>
                      <td>{lead.email}</td>
                      <td>{lead.service}</td>
                      <td className="mono">{formatBudget(lead.budget)}</td>
                      <td>
                        <span className={priorityPillClass(lead.priority)}>
                          {lead.priority ?? "unclassified"}
                        </span>
                      </td>
                      <td>
                        <span className="pill pill-neutral">{lead.status}</span>
                      </td>
                      <td className="mono">{formatDate(lead.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Proposals */}
        <section className="card">
          <div className="card-header">
            <div className="card-header-title">
              <FileText />
              Proposals
            </div>
            <span className="card-count">{proposals.length}</span>
          </div>
          {proposals.length === 0 ? (
            <EmptyState label="No proposals yet — agent is waiting" />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Lead</th>
                    <th>Sections</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {proposals.map((p) => (
                    <tr key={p.id}>
                      <td>{p.lead_name ?? `#${p.lead_id}`}</td>
                      <td>
                        <div className="section-badges">
                          {(["overview", "scope", "timeline", "pricing"] as const).map((section) =>
                            p[section] ? (
                              <span className="section-tag" key={section}>
                                {section}
                              </span>
                            ) : null,
                          )}
                        </div>
                      </td>
                      <td>
                        <span className="pill pill-neutral">{p.status}</span>
                      </td>
                      <td className="mono">{formatDate(p.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Delivery plans */}
        <section className="card">
          <div className="card-header">
            <div className="card-header-title">
              <Rocket />
              Delivery Plans
            </div>
            <span className="card-count">{deliveryPlans.length}</span>
          </div>
          {deliveryPlans.length === 0 ? (
            <EmptyState label="No delivery plans yet — agent is waiting" />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Lead</th>
                    <th>Steps</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {deliveryPlans.map((plan) => (
                    <tr key={plan.id}>
                      <td>{plan.lead_name ?? `#${plan.lead_id}`}</td>
                      <td>
                        <div className="steps-row">
                          {DELIVERY_STEP_ORDER.map((stepName) => {
                            const step = plan.steps.find((s) => s.step === stepName);
                            const done = step?.status === "done" || step?.status === "complete";
                            return (
                              <span className={`step-chip${done ? " done" : ""}`} key={stepName}>
                                {stepName}
                              </span>
                            );
                          })}
                        </div>
                      </td>
                      <td>
                        <span className="pill pill-neutral">{plan.status}</span>
                      </td>
                      <td className="mono">{formatDate(plan.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Audit log */}
        <section className="card">
          <div className="card-header">
            <div className="card-header-title">
              <ShieldCheck />
              Audit Log
            </div>
            <span className="card-count">{auditLog.length}</span>
          </div>
          {auditLog.length === 0 ? (
            <EmptyState label="No audit log entries yet — agent is waiting" />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Target</th>
                    <th>Result</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLog.map((entry) => (
                    <tr key={entry.id}>
                      <td>{entry.action}</td>
                      <td className="mono">{entry.target ?? "—"}</td>
                      <td>
                        <span className={`pill ${entry.result === "ok" ? "pill-ok" : "pill-rejected"}`}>
                          {entry.result}
                        </span>
                      </td>
                      <td className="mono">{formatDate(entry.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
