import type { NextConfig } from "next";
import path from "node:path";

// Standalone output: self-contained server bundle for the Phase 5 VPS deploy.
// outputFileTracingRoot pins the workspace root to this project — a stray
// lockfile in a parent directory otherwise makes Next.js misdetect it.
const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;
