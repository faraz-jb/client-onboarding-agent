#!/usr/bin/env node
/**
 * Runner for the RAG groundedness suite — `npm run rag`.
 *
 * Wraps `promptfoo eval` for one reason: promptfoo keeps its run history in a
 * SQLite DB under a single machine-global config dir (~/.promptfoo) shared by
 * every project on the box. When that DB's schema is out of sync with the
 * installed promptfoo version, the CLI aborts during migration before it runs
 * a single test case — a failure that has nothing to do with this suite.
 *
 * Pinning PROMPTFOO_CONFIG_DIR to a gitignored dir inside the repo makes the
 * eval hermetic: its history is per-project, it cannot be broken by an
 * unrelated project's promptfoo state, and it reproduces the same way on a
 * clean CI runner as it does locally.
 *
 * Extra CLI args pass straight through: `npm run rag -- --no-cache`.
 */

const { spawnSync } = require('node:child_process');
const path = require('node:path');

const REPO_ROOT = path.resolve(__dirname, '..');
const CONFIG_PATH = path.join(REPO_ROOT, 'evals', 'rag-groundedness.yaml');
const PROMPTFOO_BIN = path.join(
  REPO_ROOT,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'promptfoo.cmd' : 'promptfoo'
);

const result = spawnSync(PROMPTFOO_BIN, ['eval', '-c', CONFIG_PATH, ...process.argv.slice(2)], {
  cwd: REPO_ROOT,
  stdio: 'inherit',
  // shell:true is required on Windows to execute the .cmd shim.
  shell: process.platform === 'win32',
  env: {
    ...process.env,
    PROMPTFOO_CONFIG_DIR: path.join(REPO_ROOT, '.promptfoo'),
    // The suite is retrieval-only and must never phone home to grade a case.
    PROMPTFOO_DISABLE_TELEMETRY: '1',
    PROMPTFOO_DISABLE_UPDATE: '1',
  },
});

if (result.error) {
  console.error(`[rag] failed to launch promptfoo: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
