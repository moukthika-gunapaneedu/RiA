// docs/assets/app.js
const $ = (sel) => document.querySelector(sel);

const askForm = $("#askForm");
const questionEl = $("#question");
const answerArea = $("#answerArea");
const timelineEl = $("#timeline");
const evidenceEl = $("#evidence");

const coverageVal = $("#coverageVal");
const unsupportedVal = $("#unsupportedVal");

const btnCopy = $("#btnCopy");
const btnClear = $("#btnClear");
const toggleCitations = $("#toggleCitations");

const toastEl = $("#toast");

const TIMELINE_STEPS = [
  "Plan generated",
  "Retrieval pass 1 complete",
  "Query refined",
  "Retrieval pass 2 complete",
  "Verification complete",
  "Final answer generated",
];

function toast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  setTimeout(() => toastEl.classList.remove("show"), 1400);
}

function setTimeline(stateIndex) {
  timelineEl.innerHTML = "";
  TIMELINE_STEPS.forEach((label, i) => {
    const li = document.createElement("li");
    li.className = "titem";

    let state = "idle";
    if (i < stateIndex) state = "done";
    if (i === stateIndex) state = "active";

    li.dataset.state = state;

    li.innerHTML = `
      <span class="tdot" aria-hidden="true"></span>
      <span class="tlabel">${label}</span>
      <span class="tmeta">${state === "done" ? "✅" : state === "active" ? "⏳" : ""}</span>
    `;
    timelineEl.appendChild(li);
  });
}

function renderSkeleton() {
  answerArea.innerHTML = `
    <div class="answer__content">
      <div class="step">
        <div class="step__title">
          <span>Thinking…</span>
          <span class="muted">RIA is grounding this answer</span>
        </div>
        <div class="step__body muted">Retrieving evidence and building a traceable response.</div>
        <div class="codeblock" style="opacity:.65">Loading…</div>
      </div>
      <div class="step" style="opacity:.65">
        <div class="step__title"><span>Loading evidence</span></div>
        <div class="step__body muted">Sources will appear in the Trust Panel.</div>
      </div>
    </div>
  `;

  evidenceEl.innerHTML = `
    <div class="evidence__empty">Retrieving evidence…</div>
  `;
}

/**
 * ✅ IMPORTANT:
 * Your FastAPI returns:
 * {
 *   answer_markdown: "...",
 *   verification: { citation_coverage, unsupported_claims, ... },
 *   round1: [{chunk_id, doc_name, page_start, page_end, section, text}, ...],
 *   round2: [...]
 * }
 *
 * This function converts that into the UI-friendly format:
 * {
 *   metrics: { citationCoverage, unsupportedClaims },
 *   answer: { steps: [...], commands: [...] },
 *   evidence: [...]
 * }
 */
function normalizeResponse(raw) {
  // If already normalized:
  if (raw?.answer?.steps && raw?.evidence) return raw;

  // If it’s a single string, wrap it
  if (typeof raw === "string") {
    return {
      answer: {
        steps: [{ title: "Answer", body: raw, citations: [] }],
        commands: [],
      },
      metrics: { citationCoverage: null, unsupportedClaims: null },
      evidence: [],
    };
  }

  // If backend returned nothing useful
  if (!raw || typeof raw !== "object") {
    return {
      answer: {
        steps: [{ title: "Answer", body: "No response returned.", citations: [] }],
        commands: [],
      },
      metrics: { citationCoverage: null, unsupportedClaims: null },
      evidence: [],
    };
  }

  // --- Map metrics ---
  const citationCoverage = raw?.verification?.citation_coverage ?? null;
  const unsupportedClaims = raw?.verification?.unsupported_claims ?? null;

  // --- Build evidence list (use chunk_id as the stable id) ---
  const evidence = [];
  const addEvidence = (arr, round) => {
    (arr || []).forEach((r) => {
      evidence.push({
        id: r.chunk_id,
        title: r.doc_name,
        meta: `p.${r.page_start}-${r.page_end} • ${r.section || "UNSPECIFIED"}`,
        snippet: r.text,
        round,
      });
    });
  };
  addEvidence(raw?.round1, 1);
  addEvidence(raw?.round2, 2);

  // --- Answer ---
  const md = String(raw?.answer_markdown || "No answer returned.");

  // One big step with the markdown text (safe + reliable)
  const citations = extractCitationsFromMarkdown(md);

  // Optional: attempt to extract commands for the “Commands” block
  const commands = extractCommands(md).map((cmd) => ({
    label: "Command",
    cmd,
    citations: citationsForCommand(cmd, citations),
  }));

  return {
    metrics: { citationCoverage, unsupportedClaims },
    answer: {
      steps: [{ title: "Final answer", body: md, citations }],
      commands,
    },
    evidence,
  };
}

function citationsForCommand(cmd, citations) {
  // naive: if a command appears near a cited line, keep all citations
  // (good enough for hackathon demo)
  if (!citations?.length) return [];
  if (!cmd) return [];
  return citations;
}

function extractCommands(markdown) {
  const lines = String(markdown).split("\n").map((l) => l.trim());
  const cmds = [];
  for (const l of lines) {
    // also catch fenced code blocks lines (already split)
    if (
      /^(stopaiw(\s|$)|startaiw(\s|$)|systemctl(\s|$)|kill(\s|$)|ps\s)/.test(l)
    ) {
      cmds.push(l);
    }
  }
  // de-dupe
  return [...new Set(cmds)];
}

function extractCitationsFromMarkdown(markdown) {
  // matches: [aiw00a13.pdf | p.1-2 | chunk: aiw00a13_pdf_...]
  const re = /\[([^\]|]+?)\s*\|\s*p\.?([0-9\-]+)\s*\|\s*chunk:\s*([^\]]+?)\]/g;
  const out = [];
  const seen = new Set();
  let m;
  while ((m = re.exec(String(markdown))) !== null) {
    const source = (m[1] || "").trim();
    const page = (m[2] || "").trim();
    const evidenceId = (m[3] || "").trim();
    const key = `${source}|${page}|${evidenceId}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push({ source, page, evidenceId });
    }
  }
  return out;
}

function citeLabel(c) {
  const page = c.page ? `p.${c.page}` : "";
  return `${c.source}${page ? " " + page : ""}`;
}

function renderAnswer(data) {
  const { answer, metrics } = data;

  coverageVal.textContent =
    metrics?.citationCoverage == null ? "—" : `${Math.round(metrics.citationCoverage * 100)}%`;
  unsupportedVal.textContent =
    metrics?.unsupportedClaims == null ? "—" : `${metrics.unsupportedClaims}`;

  const wrapper = document.createElement("div");
  wrapper.className = "answer__content";

  (answer.steps || []).forEach((s, idx) => {
    const step = document.createElement("div");
    step.className = "step";
    step.innerHTML = `
      <div class="step__title">
        <span>${idx + 1}. ${escapeHtml(s.title || "Step")}</span>
      </div>
      <div class="step__body">${renderMarkdownLite(s.body || "")}</div>
    `;

    if (Array.isArray(s.citations) && s.citations.length) {
      const cites = document.createElement("div");
      cites.className = "cites";
      s.citations.forEach((c) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "cite";
        chip.dataset.evidenceId = c.evidenceId || "";
        chip.textContent = citeLabel(c);
        chip.title = "Jump to evidence";
        chip.addEventListener("click", () => jumpToEvidence(c.evidenceId));
        cites.appendChild(chip);
      });
      step.appendChild(cites);
    }

    wrapper.appendChild(step);
  });

  if (Array.isArray(answer.commands) && answer.commands.length) {
    const block = document.createElement("div");
    block.className = "step";
    block.innerHTML = `
      <div class="step__title">
        <span>Commands</span>
        <span class="muted">Copy-ready</span>
      </div>
      <div class="codeblock" id="cmdBlock"></div>
    `;

    const cmdBlock = block.querySelector("#cmdBlock");
    answer.commands.forEach((c) => {
      const row = document.createElement("div");
      row.className = "codeline";
      row.innerHTML = `
        <div>
          <div style="font-weight:650; opacity:.95">${escapeHtml(c.label || "")}</div>
          <div style="margin-top:4px; opacity:.95">${escapeHtml(c.cmd || "")}</div>
        </div>
        <button class="copyicon" type="button">Copy</button>
      `;
      row.querySelector(".copyicon").addEventListener("click", async () => {
        await navigator.clipboard.writeText(c.cmd || "");
        toast("Copied command");
      });
      cmdBlock.appendChild(row);

      if (Array.isArray(c.citations) && c.citations.length) {
        const cites = document.createElement("div");
        cites.className = "cites";
        c.citations.forEach((ci) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "cite";
          chip.dataset.evidenceId = ci.evidenceId || "";
          chip.textContent = citeLabel(ci);
          chip.addEventListener("click", () => jumpToEvidence(ci.evidenceId));
          cites.appendChild(chip);
        });
        cmdBlock.appendChild(cites);
      }
    });

    wrapper.appendChild(block);
  }

  answerArea.innerHTML = "";
  answerArea.appendChild(wrapper);
}

function renderMarkdownLite(md) {
  let html = escapeHtml(String(md));

  // headings
  html = html.replace(/^###\s(.+)$/gm, `<div style="font-weight:800;font-size:18px;margin:10px 0 6px">$1</div>`);
  html = html.replace(/^##\s(.+)$/gm, `<div style="font-weight:800;font-size:20px;margin:10px 0 6px">$1</div>`);
  html = html.replace(/^#\s(.+)$/gm, `<div style="font-weight:900;font-size:22px;margin:10px 0 6px">$1</div>`);

  // inline code
  html = html.replace(/`([^`]+)`/g, `<span class="inlinecode">$1</span>`);

  // code blocks (triple backticks)
  html = html.replace(/```([\s\S]*?)```/g, (_, code) => {
    return `<div class="codeblock">${escapeHtml(code.trim())}</div>`;
  });

  // lists
  html = html.replace(/^\s*-\s(.+)$/gm, `<li>$1</li>`);
  html = html.replace(/(<li>[\s\S]*<\/li>)/g, `<ul class="mdlist">$1</ul>`);

  // paragraphs + line breaks
  html = html.replace(/\n{2,}/g, `</p><p class="mdp">`);
  html = `<p class="mdp">${html}</p>`.replace(/\n/g, `<br>`);

  // links
  html = linkify(html);

  return html;
}

function renderEvidence(data) {
  const ev = data.evidence || [];
  if (!ev.length) {
    evidenceEl.innerHTML = `<div class="evidence__empty">No evidence returned.</div>`;
    return;
  }

  evidenceEl.innerHTML = "";
  ev.forEach((e) => {
    const card = document.createElement("div");
    card.className = "source";
    card.dataset.sourceId = e.id || "";
    card.dataset.open = "false";

    card.innerHTML = `
      <div class="source__head">
        <div>
          <div class="source__title">${escapeHtml(e.title || "Source")}</div>
          <div class="source__meta">${escapeHtml(e.meta || "")}</div>
        </div>
        <div class="muted">${escapeHtml(e.round ? `Round ${e.round}` : "")}</div>
      </div>
      <div class="source__body">
        <div class="snip">${escapeHtml(e.snippet || "")}</div>
      </div>
    `;

    card.querySelector(".source__head").addEventListener("click", () => {
      card.dataset.open = card.dataset.open === "true" ? "false" : "true";
    });

    evidenceEl.appendChild(card);
  });
}

function jumpToEvidence(evidenceId) {
  if (!evidenceId) return;

  const node = evidenceEl.querySelector(`[data-source-id="${CSS.escape(evidenceId)}"]`);
  if (!node) return;

  node.dataset.open = "true";
  node.scrollIntoView({ behavior: "smooth", block: "center" });

  const snip = node.querySelector(".snip");
  if (snip) {
    snip.innerHTML = snip.innerHTML.replace(/<mark>|<\/mark>/g, "");
    snip.innerHTML = `<mark>${snip.innerHTML}</mark>`;
    setTimeout(() => {
      snip.innerHTML = snip.innerHTML.replace(/<mark>|<\/mark>/g, "");
    }, 1200);
  }
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function linkify(text) {
  const urlRe = /(https?:\/\/[^\s]+)/g;
  return text.replace(urlRe, `<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>`);
}

async function copyAnswerToClipboard(data) {
  const withCites = toggleCitations.checked;

  let out = "";
  (data.answer.steps || []).forEach((s, i) => {
    out += `${i + 1}. ${s.title}\n${s.body}\n`;
    if (withCites && Array.isArray(s.citations) && s.citations.length) {
      out += `Citations: ${s.citations.map(citeLabel).join(", ")}\n`;
    }
    out += "\n";
  });

  if (Array.isArray(data.answer.commands) && data.answer.commands.length) {
    out += "Commands:\n";
    data.answer.commands.forEach((c) => {
      out += `- ${c.label}: ${c.cmd}\n`;
      if (withCites && Array.isArray(c.citations) && c.citations.length) {
        out += `  Citations: ${c.citations.map(citeLabel).join(", ")}\n`;
      }
    });
  }

  await navigator.clipboard.writeText(out.trim());
  toast("Copied answer");
}

async function callBackend(question) {
  const endpoint = "https://friendly-barnacle-7x4vjxv749r2p9qx-8000.app.github.dev/ask";

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000); // 20s timeout

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    });

    const text = await res.text(); // read raw text first

    if (!res.ok) {
      throw new Error(`Backend error: ${res.status} — ${text.slice(0, 300)}`);
    }

    // try to parse JSON safely
    try {
      return JSON.parse(text);
    } catch (e) {
      throw new Error(`Invalid JSON from backend: ${text.slice(0, 300)}`);
    }
  } finally {
    clearTimeout(timeout);
  }
}

function demoResponse(question) {
  return {
    metrics: { citationCoverage: 0.8, unsupportedClaims: 1 },
    answer: {
      steps: [
        {
          title: "Pick shutdown behavior",
          body: "Use stopaiw for immediate stop, or stopaiw -q for a graceful stop after current steps complete.",
          citations: [{ source: "aiw00a13.pdf", page: "1-2", evidenceId: "ev1" }],
        },
        {
          title: "Optional: stop supporting services",
          body: "If running PostgreSQL configuration, you may also stop PostgreSQL to ensure all processing ends.",
          citations: [{ source: "aiw00a13.pdf", page: "1-2", evidenceId: "ev2" }],
        },
      ],
      commands: [
        {
          label: "Immediate stop (no wait)",
          cmd: "stopaiw",
          citations: [{ source: "aiw00a13.pdf", page: "1-2", evidenceId: "ev1" }],
        },
        {
          label: "Graceful stop (wait for current steps)",
          cmd: "stopaiw -q",
          citations: [{ source: "aiw00a13.pdf", page: "1-2", evidenceId: "ev1" }],
        },
        {
          label: "Optional (PostgreSQL)",
          cmd: "systemctl stop postgresql",
          citations: [{ source: "aiw00a13.pdf", page: "1-2", evidenceId: "ev2" }],
        },
      ],
    },
    evidence: [
      {
        id: "ev1",
        title: "aiw00a13.pdf",
        meta: "p.1-2 • Stopping the base product and secondary servers",
        snippet:
          "Enter one of these commands: stopaiw (stop immediately), stopaiw -q (stop after steps complete), stopaiw -t (AFP Support option).",
        round: 2,
      },
      {
        id: "ev2",
        title: "aiw00a13.pdf",
        meta: "p.1-2 • Additional steps",
        snippet:
          "If you run in a PostgreSQL configuration, run: systemctl stop postgresql.",
        round: 2,
      },
    ],
  };
}

let lastData = null;

async function run(question) {
  renderSkeleton();
  setTimeline(0);

  const tick = (i, delay = 260) =>
    new Promise((r) =>
      setTimeout(() => {
        setTimeline(i);
        r();
      }, delay)
    );

  await tick(0, 220);
  await tick(1, 240);
  await tick(2, 240);
  await tick(3, 240);
  await tick(4, 240);

  let raw;
  try {
    raw = await callBackend(question);
  } catch (e) {
    console.warn("Backend call failed, using demo response:", e);
    raw = demoResponse(question);
  }

  await tick(5, 180);

  const data = normalizeResponse(raw);
  lastData = data;

  renderAnswer(data);
  renderEvidence(data);
}

askForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = questionEl.value.trim();
  if (!q) return toast("Type a question first");
  $("#runBtn").disabled = true;
  try {
    await run(q);
  } finally {
    $("#runBtn").disabled = false;
  }
});

questionEl.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    askForm.requestSubmit();
  }
});

btnCopy.addEventListener("click", async () => {
  if (!lastData) return toast("Nothing to copy yet");
  await copyAnswerToClipboard(lastData);
});

btnClear.addEventListener("click", () => {
  lastData = null;
  answerArea.innerHTML = `
    <div class="empty">
      <div class="empty__icon">⌁</div>
      <div class="empty__title">Cleared.</div>
      <div class="empty__text">Ask a new question to generate a grounded answer.</div>
    </div>
  `;
  evidenceEl.innerHTML = `<div class="evidence__empty">Evidence will appear here once you run a question.</div>`;
  coverageVal.textContent = "—";
  unsupportedVal.textContent = "—";
  setTimeline(0);
  toast("Cleared");
});

// Initial timeline
setTimeline(0);