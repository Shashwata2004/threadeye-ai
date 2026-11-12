"use strict";

const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const citationStore = new Map();

function byId(id) { return document.getElementById(id); }
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function appendLabelValue(parent, label, value) {
  const term = element("dt", "", label);
  const description = element("dd", "", value ?? "Not provided");
  parent.append(term, description);
}
function setBusy(button, busy, busyText) {
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? busyText : button.dataset.label;
}
function updateCount(inputId, countId) {
  byId(countId).textContent = String(byId(inputId).value.length);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {"X-CSRF-Token": csrfToken, ...(options.headers || {})}
  });
  let payload;
  try { payload = await response.json(); }
  catch (_) { payload = {state: "BACKEND UNAVAILABLE", message: "The local UI returned an invalid response."}; }
  if (response.status === 401) window.location.assign("/");
  return {ok: response.ok, status: response.status, payload};
}

function setConnection(state, detail) {
  const chip = byId("connection-chip");
  chip.className = "connection-chip " + (state === "CONNECTED" ? "is-connected" : "is-failed");
  chip.querySelector("span:last-child").textContent = state === "CONNECTED" ? "MCP connected" : "MCP unavailable";
  byId("mcp-status").textContent = state === "CONNECTED" ? "Connected" : state;
  byId("mcp-detail").textContent = detail;
}

async function loadOverview() {
  const result = await api("/api/overview");
  if (!result.ok) {
    setConnection(result.payload.state || "BACKEND UNAVAILABLE", result.payload.message || "Authenticated backend check failed.");
    return;
  }
  const data = result.payload.data;
  setConnection("CONNECTED", `Protocol ${data.protocol_version}; server ${data.server_version}.`);
  byId("source-count").textContent = `${data.sources.source_count} source`;
  byId("scope-summary").textContent = data.authorization_scopes.join(" · ");
  const live = byId("live-policy");
  clear(live);
  const list = element("ul");
  [
    `Transport: ${data.capabilities.transport}`,
    `Answer mode: ${data.capabilities.answer_mode}`,
    `Corpus: ${data.capabilities.scope}`,
    `Top-k limit: ${data.security_policy.limits.max_top_k}`
  ].forEach(item => list.append(element("li", "", item)));
  live.append(list);
}

function rankingText(item, index) {
  const parts = [`Rank ${index + 1}`];
  if (item.retrieval_methods) parts.push(item.retrieval_methods.join(" + "));
  if (typeof item.rrf_score === "number") parts.push(`RRF ${item.rrf_score.toFixed(5)}`);
  if (typeof item.cosine_similarity === "number") parts.push(`Cosine ${item.cosine_similarity.toFixed(3)}`);
  return parts.join(" · ");
}

function renderSearch(payload) {
  const container = byId("search-results");
  clear(container);
  if (!payload.results.length) {
    container.append(element("div", "empty-state", "No authorized evidence matched this query."));
    return;
  }
  payload.results.forEach((item, index) => {
    const card = element("article", "evidence-card");
    const header = element("div", "evidence-card__header");
    const titleWrap = element("div");
    titleWrap.append(element("span", "rank-label", rankingText(item, index)), element("h3", "", item.source_title));
    header.append(titleWrap, element("code", "chunk-code", item.chunk_id));
    const excerpt = element("p", "evidence-excerpt", item.sanitized_text);
    const meta = element("div", "evidence-meta");
    meta.append(element("span", "", `Source ${item.source_relative_path}`), element("span", "", `Span ${item.normalized_start}–${item.normalized_end}`));
    card.append(header, excerpt, meta);
    container.append(card);
  });
}

async function runSearch() {
  const button = byId("search-form").querySelector('button[type="submit"]');
  setBusy(button, true, "Searching…");
  byId("search-status").className = "result-status is-loading";
  byId("search-status").textContent = "Running an authenticated MCP evidence search.";
  clear(byId("search-results"));
  const result = await api("/api/search", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({query: byId("search-query").value, mode: byId("search-mode").value, top_k: Number(byId("search-top-k").value)})
  });
  setBusy(button, false, "");
  byId("search-status").className = `result-status ${result.ok ? "is-success" : "is-error"}`;
  byId("search-status").textContent = result.ok ? `${result.payload.data.result_count} authorized result(s) returned through MCP.` : `${result.payload.state}: ${result.payload.message}`;
  if (result.ok) renderSearch(result.payload.data);
}

function statusClass(state) {
  if (state === "ANSWERED") return "answer-badge is-answered";
  if (state === "ABSTAINED") return "answer-badge is-abstained";
  return "answer-badge is-failed";
}

function registerCitation(citation) {
  const id = `citation-${citationStore.size + 1}`;
  citationStore.set(id, citation);
  return id;
}

function renderAnswer(state, payload) {
  const container = byId("answer-result");
  clear(container);
  const header = element("div", "answer-header");
  header.append(element("span", statusClass(state), state), element("span", "answer-mode", `${payload.answer_mode || "extractive"} · ${payload.retrieval_mode || "hybrid"}`));
  container.append(header);
  if (state === "ANSWERED") {
    container.append(element("blockquote", "answer-text", payload.answer));
    const note = element("p", "verified-note", "✓ Citation contract validated by the evidence service and display boundary.");
    container.append(note);
    const citations = element("div", "citation-list");
    payload.citations.forEach((citation, index) => {
      const button = element("button", "citation-button");
      button.type = "button";
      button.dataset.citation = registerCitation(citation);
      button.append(element("span", "", `Citation ${index + 1}`), element("strong", "", citation.heading_hierarchy.join(" › ") || citation.source_relative_path), element("small", "", `Chunk ${citation.chunk_id}`));
      citations.append(button);
    });
    container.append(citations);
  } else {
    const abstention = element("div", "abstention-card");
    abstention.append(element("strong", "", "No answer was generated."), element("p", "", `Reason: ${payload.abstention_reason || "The request could not be supported safely."}`));
    container.append(abstention);
  }
  container.append(element("p", "human-note", "Human Verification Recommended — this companion cannot approve rolls, change scores, or replace supervisor review."));
}

async function runAnswer() {
  const button = byId("ask-form").querySelector('button[type="submit"]');
  setBusy(button, true, "Checking evidence…");
  byId("answer-status").className = "result-status is-loading";
  byId("answer-status").textContent = "Running authenticated MCP retrieval, extraction, and citation validation.";
  clear(byId("answer-result"));
  const result = await api("/api/answer", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({question: byId("ask-question").value, mode: byId("ask-mode").value})
  });
  setBusy(button, false, "");
  byId("answer-status").className = `result-status ${result.ok ? "is-success" : "is-error"}`;
  byId("answer-status").textContent = result.ok ? `${result.payload.state}: evidence processing completed.` : `${result.payload.state}: ${result.payload.message}`;
  if (result.payload.data) renderAnswer(result.payload.state, result.payload.data);
}

function showCitation(citation) {
  const metadata = byId("citation-metadata");
  clear(metadata);
  appendLabelValue(metadata, "Safe source identifier", citation.source_relative_path);
  appendLabelValue(metadata, "Chunk reference", citation.chunk_id);
  appendLabelValue(metadata, "Heading", citation.heading_hierarchy.join(" › "));
  appendLabelValue(metadata, "Normalized location", `${citation.normalized_start}–${citation.normalized_end}`);
  appendLabelValue(metadata, "Processing version", citation.processing_version);
  appendLabelValue(metadata, "Authorization reference", citation.authorization_reference);
  byId("citation-excerpt").textContent = citation.excerpt;
  byId("citation-dialog").showModal();
}

byId("search-query").addEventListener("input", () => updateCount("search-query", "search-count"));
byId("ask-question").addEventListener("input", () => updateCount("ask-question", "ask-count"));
byId("search-form").addEventListener("submit", event => { event.preventDefault(); runSearch(); });
byId("ask-form").addEventListener("submit", event => { event.preventDefault(); runAnswer(); });
document.addEventListener("click", event => {
  const citationButton = event.target.closest("[data-citation]");
  if (citationButton) showCitation(citationStore.get(citationButton.dataset.citation));
  const demo = event.target.closest("[data-demo]");
  if (demo && demo.dataset.demo === "search") {
    byId("search-query").value = "content hash sanitized observation";
    byId("search-mode").value = "hybrid"; byId("search-top-k").value = "3"; updateCount("search-query", "search-count");
    byId("search").scrollIntoView({behavior: "smooth"}); runSearch();
  }
  if (demo && demo.dataset.demo === "answer") {
    byId("ask-question").value = "Which supplier lot is recorded for ROLL-NST-204?";
    byId("ask-mode").value = "hybrid"; updateCount("ask-question", "ask-count");
    byId("ask").scrollIntoView({behavior: "smooth"}); runAnswer();
  }
  if (demo && demo.dataset.demo === "abstain") {
    byId("ask-question").value = "What is tomorrow's weather in Dhaka?";
    byId("ask-mode").value = "hybrid"; updateCount("ask-question", "ask-count");
    byId("ask").scrollIntoView({behavior: "smooth"}); runAnswer();
  }
});
byId("citation-close").addEventListener("click", () => byId("citation-dialog").close());
byId("logout-button").addEventListener("click", async () => { await api("/api/logout", {method: "POST"}); window.location.assign("/"); });

loadOverview();
