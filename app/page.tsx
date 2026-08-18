import React from "react";
import Link from "next/link";
import {
  ArrowRight,
  UserPlus,
  BrainCircuit,
  FileText,
  Rocket,
  ExternalLink,
  LayoutDashboard,
} from "lucide-react";

const FLOW = [
  {
    icon: UserPlus,
    title: "Lead",
    desc: "Raw contact — name, email, service, budget — captured at first touch.",
  },
  {
    icon: BrainCircuit,
    title: "Gemini analysis",
    desc: "Brain agent qualifies and reasons over the lead; a fast sub-agent classifies priority.",
  },
  {
    icon: FileText,
    title: "Proposal",
    desc: "Overview, scope, timeline, and pricing drafted from what the client actually said.",
  },
  {
    icon: Rocket,
    title: "Delivery plan",
    desc: "Discovery, build, review, handover — a concrete handoff, not a vague promise.",
  },
];

const STACK = ["Gemini 3.5 Pro", "Gemini 3 Flash", "Google ADK", "Next.js 15", "SQLite"];

export default function LandingPage() {
  return (
    <>
      <div className="shell">
        <nav className="nav">
          <div className="nav-brand">
            <span className="dot" />
            Client Onboarding Agent
          </div>
          <div className="nav-links">
            <Link href="/dashboard">Dashboard</Link>
            <a href="https://github.com/faraz-jb/client-onboarding-agent" target="_blank" rel="noreferrer">
              GitHub
            </a>
          </div>
        </nav>

        <section className="hero">
          <span className="eyebrow">All Things Agentic Hackathon</span>
          <h1>
            Client Onboarding Agent — from lead to delivery,
            <br />
            no friction.
          </h1>
          <p>
            An ADK-powered agent that carries a raw lead through qualification, a drafted
            proposal, and a delivery handoff plan — with a full audit trail at every step.
          </p>
          <div className="cta-row">
            <Link href="/dashboard" className="btn btn-primary">
              <LayoutDashboard size={16} />
              View Dashboard
              <ArrowRight size={16} />
            </Link>
            <a
              href="https://github.com/faraz-jb/client-onboarding-agent"
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary"
            >
              <ExternalLink size={16} />
              View Source
            </a>
          </div>
        </section>

        <div className="diagram">
          {FLOW.map((node, i) => (
            <React.Fragment key={node.title}>
              <div className="diagram-node">
                <div className="icon-wrap">
                  <node.icon size={20} />
                </div>
                <h3>{node.title}</h3>
                <p>{node.desc}</p>
              </div>
              {i < FLOW.length - 1 && (
                <div className="diagram-arrow">
                  <ArrowRight size={20} />
                </div>
              )}
            </React.Fragment>
          ))}
        </div>

        <div className="badges">
          {STACK.map((s) => (
            <span className="badge" key={s}>
              <BrainCircuit />
              {s}
            </span>
          ))}
        </div>
      </div>

      <footer>Built for the Google All Things Agentic Hackathon.</footer>
    </>
  );
}
