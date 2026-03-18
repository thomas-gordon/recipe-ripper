const SERVER = "http://localhost:5050";

const btn       = document.getElementById("convert");
const btnLabel  = document.getElementById("btn-label");
const spinner   = document.getElementById("spinner");
const statusEl  = document.getElementById("status");
const hintEl    = document.getElementById("hint");
const recipeName = document.getElementById("recipe-name");
const recipeLabel = document.getElementById("recipe-label");
const noteBtn     = document.getElementById("apple-note-btn");
const noteBtnLabel = document.getElementById("note-btn-label");
const noteSpinner  = document.getElementById("note-spinner");

let pageData = null;   // { blocks: [...], url: "..." }
let serverOk = false;

// ── Helpers ─────────────────────────────────────────────────────────────────

function setStatus(msg, type = "") {
  statusEl.textContent = msg;
  statusEl.className = type;
}

function setConverting(on) {
  btn.disabled = on || !serverOk || !pageData?.hasRecipe;
  spinner.classList.toggle("active", on);
  btnLabel.textContent = on ? "Generating PDF…" : "Convert to PDF";
}

function setSavingNote(on) {
  noteBtn.disabled = on || !serverOk || !pageData?.hasRecipe;
  noteSpinner.classList.toggle("active", on);
  noteBtnLabel.style.display = on ? "none" : "";
  noteSpinner.style.display  = on ? "block" : "";
}

/** Try to extract a recipe title from the JSON-LD blocks in the page. */
function extractTitle(blocks) {
  for (const block of blocks) {
    let data;
    try { data = JSON.parse(block); } catch { continue; }
    const items = Array.isArray(data) ? data : [data];
    // Unwrap @graph
    const graph = items.find(i => i?.["@graph"]);
    const list = graph ? graph["@graph"] : items;
    for (const item of list) {
      const t = [].concat(item?.["@type"] || []).join(" ");
      if (t.includes("Recipe")) return item.name || null;
    }
  }
  return null;
}

// ── 1. Check server health ───────────────────────────────────────────────────

async function checkServer() {
  try {
    const r = await fetch(`${SERVER}/health`, { signal: AbortSignal.timeout(2000) });
    if (r.ok) {
      serverOk = true;
      hintEl.classList.remove("visible");
      return true;
    }
  } catch (_) {}
  serverOk = false;
  setStatus("Server not running — see hint below", "error");
  hintEl.classList.add("visible");
  return false;
}

// ── 2. Scrape JSON-LD from the active tab ────────────────────────────────────

async function scrapeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  let results;
  try {
    results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
        return {
          blocks: Array.from(scripts).map(s => s.textContent || ""),
          url: window.location.href,
        };
      },
    });
  } catch (e) {
    // Chrome extension pages, PDF viewer, etc. can't be scripted
    return null;
  }

  return results?.[0]?.result ?? null;
}

// ── 3. Initialise popup ──────────────────────────────────────────────────────

(async () => {
  // Run server check and page scrape in parallel
  const [ok, data] = await Promise.all([checkServer(), scrapeTab()]);

  if (!data) {
    recipeLabel.textContent = "Can't read this page";
    recipeName.className = "not-found";
    return;
  }

  pageData = data;
  const title = extractTitle(data.blocks);

  if (title) {
    pageData.hasRecipe = true;
    recipeLabel.textContent = title;
    recipeName.className = "found";
    if (ok) {
      btn.disabled = false;
      noteBtn.disabled = false;
      setStatus("");
    }
  } else {
    pageData.hasRecipe = false;
    recipeLabel.textContent = "No recipe detected on this page";
    recipeName.className = "not-found";
    if (ok) setStatus("Open a recipe page first", "error");
  }
})();

// ── 4. Convert button ────────────────────────────────────────────────────────

btn.addEventListener("click", async () => {
  setConverting(true);
  setStatus("");

  let response;
  try {
    response = await fetch(`${SERVER}/convert`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonld_blocks: pageData.blocks,
        url: pageData.url,
      }),
      signal: AbortSignal.timeout(30000),  // 30 s for PDF generation
    });
  } catch (e) {
    setStatus("Could not reach server — is it still running?", "error");
    setConverting(false);
    return;
  }

  if (!response.ok) {
    let msg = `Server error ${response.status}`;
    try {
      const body = await response.json();
      msg = body.error || msg;
    } catch (_) {}
    setStatus(msg, "error");
    setConverting(false);
    return;
  }

  // Trigger browser download
  try {
    const blob = await response.blob();
    const dlUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");

    // Try to get the filename from the Content-Disposition header
    const cd = response.headers.get("Content-Disposition") || "";
    const match = cd.match(/filename="?([^";\n]+)"?/);
    a.download = match ? match[1] : "recipe_metric.pdf";

    a.href = dlUrl;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(dlUrl), 5000);

    setStatus("✓ PDF downloaded!", "success");
  } catch (e) {
    setStatus("Download failed — try again", "error");
  }

  setConverting(false);
});

// ── 5. Apple Note button ─────────────────────────────────────────────────────

noteBtn.addEventListener("click", async () => {
  setSavingNote(true);
  setStatus("");

  let response;
  try {
    response = await fetch(`${SERVER}/apple-note`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonld_blocks: pageData.blocks,
        url: pageData.url,
      }),
      signal: AbortSignal.timeout(15000),
    });
  } catch (e) {
    setStatus("Could not reach server — is it still running?", "error");
    setSavingNote(false);
    return;
  }

  if (!response.ok) {
    let msg = `Server error ${response.status}`;
    try {
      const body = await response.json();
      msg = body.error || msg;
    } catch (_) {}
    setStatus(msg, "error");
    setSavingNote(false);
    return;
  }

  const data = await response.json();
  setStatus(`✓ Saved "${data.title}" to Apple Notes!`, "success");
  setSavingNote(false);
});
