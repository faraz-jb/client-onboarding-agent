import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

// Spawns the Python ADK agent as a fire-and-forget subprocess for a given
// lead. Shared by POST /api/leads (auto-process every incoming lead) and
// POST /api/agent/process-lead (manual re-trigger).
//
// Returns false when the venv python is missing — the caller decides how to
// surface that (500 vs silent skip).
export function spawnAgentForLead(leadId: number): boolean {
  const projectRoot = process.cwd();
  const pythonPath =
    process.platform === "win32"
      ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
      : path.join(projectRoot, ".venv", "bin", "python");

  if (!existsSync(pythonPath)) return false;

  const child = spawn(pythonPath, ["-m", "agent.agent", "--lead-id", String(leadId)], {
    cwd: projectRoot,
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stdout.on("data", (chunk: Buffer) => {
    console.log(`[agent:${leadId}]`, chunk.toString().trim());
  });
  child.stderr.on("data", (chunk: Buffer) => {
    console.error(`[agent:${leadId}]`, chunk.toString().trim());
  });
  child.on("error", (err) => {
    console.error(`[agent:${leadId}] failed to spawn`, err);
  });

  return true;
}
