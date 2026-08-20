/**
 * Promptfoo provider: retrieval-only.
 *
 * Runs the real production retriever (agent/rag.py) through
 * scripts/rag_query.py and returns the retrieved chunk text as the output.
 * No LLM is called anywhere in this path, so the groundedness suite is
 * deterministic and grades retrieval itself: if a `contains` assertion fails,
 * the fact never reached the model, which is the failure that matters.
 *
 * Backend-agnostic by design — Chroma serves the query when the vector store
 * and an embedding key are present, keyword tf-idf otherwise. The suite is
 * written so every assertion holds either way.
 */

const { execFileSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

const REPO_ROOT = path.resolve(__dirname, '..');
const QUERY_SCRIPT = path.join(REPO_ROOT, 'scripts', 'rag_query.py');

// Retrieval is fast, but a cold Chroma import plus an embedding round-trip is
// not instant — this bounds a hung call without tripping on a slow first run.
const TIMEOUT_MS = 60_000;

/**
 * Resolve the Python interpreter: an explicit override wins, then the repo
 * venv for whichever platform's layout is on disk, then whatever `python` the
 * PATH provides.
 */
function resolvePython() {
  const override = process.env.RAG_PYTHON;
  if (override) return override;

  const candidates = [
    path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe'), // Windows
    path.join(REPO_ROOT, '.venv', 'bin', 'python'), // POSIX
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) ?? 'python';
}

class RagProvider {
  constructor(options = {}) {
    this.config = options.config ?? {};
    this.providerId = options.id ?? 'rag-retriever';
  }

  id() {
    return this.providerId;
  }

  /**
   * @param {string} prompt   rendered prompt — used only as a query fallback
   * @param {object} context  promptfoo context; the query lives in context.vars.query
   */
  async callApi(prompt, context) {
    const query = String(context?.vars?.query ?? prompt ?? '').trim();
    if (!query) {
      return { error: 'rag-provider: no query supplied (set the `query` var)' };
    }

    const topK = Number(this.config.topK ?? 3);

    let stdout;
    try {
      stdout = execFileSync(resolvePython(), [QUERY_SCRIPT, query, String(topK)], {
        cwd: REPO_ROOT,
        timeout: TIMEOUT_MS,
        encoding: 'utf8',
        maxBuffer: 8 * 1024 * 1024,
        windowsHide: true,
      });
    } catch (err) {
      // Surface the interpreter's own stderr — a broken venv or a missing
      // dependency should read as that, not as a generic assertion failure.
      const detail = (err.stderr || err.message || '').toString().trim();
      return { error: `rag-provider: retrieval failed: ${detail}` };
    }

    let payload;
    try {
      payload = JSON.parse(stdout);
    } catch {
      return { error: `rag-provider: unparseable retriever output: ${stdout.slice(0, 500)}` };
    }

    const chunks = Array.isArray(payload.chunks) ? payload.chunks : [];
    // The joined chunk text IS the output under assertion — the same text
    // build_knowledge_context() puts in front of the model.
    const output = chunks.map((chunk) => String(chunk.text ?? '').trim()).join('\n---\n');

    return {
      output,
      metadata: {
        backend: payload.backend ?? 'none',
        count: chunks.length,
        sources: chunks.map((chunk) => chunk.source),
      },
    };
  }
}

module.exports = RagProvider;
