// textarea autoresize
function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

// ===== CONFIG (server-side drafts, per-user) =====
const FORM_ID = "pcrForm";
const AUTOSAVE_MS = 400;

// Get user id injected by server (prefer window.APP, fallback to data-user-id on <body>)
const USER_ID =
  (window.APP && window.APP.userId) ||
  document.body.getAttribute("data-user-id") ||
  "anon";

// ===== contenteditable cell ids (MAKE SURE THESE ARE UNIQUE IN HTML) =====
const CE_IDS = [
  // First vitals table
  "time1","time2","time3","time4","time5","time6",
  "pulse1","pulse2","pulse3","pulse4","pulse5","pulse6",
  "resp1","resp2","resp3","resp4","resp5","resp6",
  "bp1","bp2","bp3","bp4","bp5","bp6",
  "loc1","loc2","loc3","loc4","loc5","loc6",
  "skin1","skin2","skin3","skin4","skin5","skin6",

  // Second vitals table (renamed to avoid duplicate IDs)
  "v2_time1","v2_time2","v2_time3","v2_time4","v2_time5","v2_time6",

  // SPO2 row
  "spo21","spo22","spo23","spo24","spo25","spo26"
];

// ===== State =====
const form = document.getElementById(FORM_ID);
const canvas = document.getElementById("injuryCanvas");
const ctx = canvas.getContext("2d");
const injuryImage = document.getElementById("injuryImage");
const resetImageBtn = document.getElementById("resetImageBtn");

let injuryPoints = []; // [{x,y}, ...]
let saveTimer;
let suppressAutosave = false; // prevents autosave during clear/reset

// ---- No-op guards for inline handlers present in HTML ----
function checkOtherText(){ /* placeholder to avoid ReferenceError */ }
function checkVisitorText(){ /* placeholder to avoid ReferenceError */ }

// ===== Helpers =====
function drawCircle(x, y) {
  ctx.beginPath();
  ctx.arc(x, y, 10, 0, 2 * Math.PI);
  ctx.fillStyle = "red";
  ctx.fill();
}

function loadImageToCanvas(imageSrc, cb) {
  const img = new Image();
  img.src = imageSrc;
  img.onload = function () {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    if (typeof cb === "function") cb();
  };
}

function collectContentEditable(ids) {
  const out = {};
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) out[id] = el.innerText.trim();
  });
  return out;
}

function serializeForm(formEl) {
  const data = {};
  const fd = new FormData(formEl);

  // inputs + checkbox arrays (name="...[]")
  fd.forEach((value, key) => {
    if (key.endsWith("[]")) {
      const base = key.slice(0, -2);
      if (!Array.isArray(data[base])) data[base] = [];
      data[base].push(value);
    } else if (!(key in data)) {
      data[key] = value;
    }
  });

  // radios
  formEl.querySelectorAll('input[type="radio"]').forEach(r => {
    if (r.checked) data[r.name] = r.value;
  });

  // contenteditable
  Object.assign(data, collectContentEditable(CE_IDS));

  // canvas points
  data.injuryPoints = injuryPoints.slice();

  // stamp user_id so you can debug
  data._userId = USER_ID;

  return data;
}

function restoreForm(formEl, data) {
  if (!data) return;

  // arrays (checkbox groups)
  for (const [key, val] of Object.entries(data)) {
    if (Array.isArray(val)) {
      val.forEach(v => {
        const box = formEl.querySelector(
          `input[name="${key}[]"][value="${CSS.escape(v)}"]`
        );
        if (box) box.checked = true;
      });
    }
  }

  // radios + regular inputs
  for (const [key, val] of Object.entries(data)) {
    if (Array.isArray(val) || key === "injuryPoints" || CE_IDS.includes(key)) continue;

    const radio = formEl.querySelector(
      `input[type="radio"][name="${key}"][value="${CSS.escape(val)}"]`
    );
    if (radio) { radio.checked = true; continue; }

    const el = formEl.elements[key];
    if (el && "value" in el) el.value = val ?? "";
  }

  // contenteditable
  CE_IDS.forEach(id => {
    if (data[id] != null) {
      const el = document.getElementById(id);
      if (el) el.innerText = data[id];
    }
  });

  // canvas points (draw after image is drawn)
  if (Array.isArray(data.injuryPoints)) {
    injuryPoints = data.injuryPoints.slice();
    injuryPoints.forEach(p => drawCircle(p.x, p.y));
  }
}

// --- server draft helpers ---
async function saveDraftToServer(payload) {
  await fetch("/submit_draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload)
  });
}

function autosave() {
  if (suppressAutosave) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    saveDraftToServer(serializeForm(form)).catch(console.error);
  }, AUTOSAVE_MS);
}

// --- reset/clear helpers ---
function resetFormUI() {
  suppressAutosave = true;

  // 1) Reset standard inputs & textareas
  form.reset();

  // 2) Clear radios/checkboxes explicitly
  form.querySelectorAll('input[type="radio"], input[type="checkbox"]').forEach(el => {
    el.checked = false;
  });

  // 3) Clear contenteditable cells
  CE_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerText = "";
  });

  // 4) Clear canvas marks & redraw base image
  injuryPoints = [];
  const originalImageSrc = injuryImage.getAttribute("data-original-src") || injuryImage.src;
  loadImageToCanvas(originalImageSrc);

  // 5) Clear custom "Other" fields
  ["sexOtherText","airwayOtherText","reasonO2OtherText","visitorText"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });

  setTimeout(() => { suppressAutosave = false; }, 300);
}

// ===== Init once DOM is ready =====
document.addEventListener("DOMContentLoaded", async () => {
  // 1) draw the base image
  const originalImageSrc = injuryImage.getAttribute("data-original-src") || injuryImage.src;
  loadImageToCanvas(originalImageSrc);

  // 2) restore from server draft
  try {
    const r = await fetch("/get_draft", { credentials: "same-origin" });
    if (r.status === 200) {
      const { draft } = await r.json();
      if (draft) {
        let data = {};
        try { data = JSON.parse(draft); } catch { /* tolerate older repr */ }
        loadImageToCanvas(originalImageSrc, () => restoreForm(form, data));
      }
    } else if (r.status !== 404) {
      console.warn("Unexpected get_draft status:", r.status);
    }
  } catch (e) {
    console.warn("Error restoring draft:", e);
  }

  // 3) canvas click → add point + draw + autosave
  canvas.addEventListener("click", (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = Math.round(e.clientX - rect.left);
    const y = Math.round(e.clientY - rect.top);
    injuryPoints.push({ x, y });
    drawCircle(x, y);
    autosave();
  });

  // 4) reset image → clear points + redraw base image
  resetImageBtn.addEventListener("click", () => {
    injuryPoints = [];
    loadImageToCanvas(originalImageSrc);  // clears + redraws image
    autosave();
  });

  // 5) inputs: autosave
  form.addEventListener("input", autosave);
  form.addEventListener("change", autosave);

  // 6) contenteditable: autosave
  CE_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", autosave);
  });

  // 7) page hide/unload: best-effort save
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      saveDraftToServer(serializeForm(form)).catch(() => {});
    }
  });
  window.addEventListener("beforeunload", () => {
    try {
      navigator.sendBeacon?.("/submit_draft",
        new Blob([JSON.stringify(serializeForm(form))], { type: "application/json" })
      );
    } catch {}
  });
});

// ===== Logout (force-save draft) =====
const logoutBtn = document.getElementById("logoutButton");
if (logoutBtn) {
  logoutBtn.addEventListener("click", async (e) => {
    try {
      const payload = serializeForm(form);
      const data = JSON.stringify(payload);
      const blob = new Blob([data], { type: "application/json" });

      let sent = false;
      if (navigator.sendBeacon) {
        sent = navigator.sendBeacon("/submit_draft", blob);
      }
      if (!sent) {
        await fetch("/submit_draft", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: data,
          credentials: "same-origin",
          keepalive: true
        });
      }
    } catch (err) {
      console.warn("Could not save draft on logout:", err);
    } finally {
      window.location.href = "/logout";
    }
  });
}

// ===== Clear Draft =====
const clearBtn = document.getElementById("clearDraftBtn");
if (clearBtn) {
  clearBtn.addEventListener("click", async () => {
    suppressAutosave = true;
    try {
      const res = await fetch("/api/clear_draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin"
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert("Could not clear draft: " + (err.error || err.message || res.status));
        return;
      }

      resetFormUI();
      alert("Draft cleared.");
    } catch (e) {
      console.error(e);
      alert("Network error clearing draft.");
    } finally {
      setTimeout(() => { suppressAutosave = false; }, 300);
    }
  });
}

// ===== Submit (server clears draft on success) =====
document.getElementById("pcrForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = serializeForm(e.currentTarget);

  try {
    const res = await fetch("/api/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin"
    });
    const out = await res.json();
    if (res.ok) {
      alert("Submitted!");
      e.currentTarget.reset();
      injuryPoints = [];
      const originalImageSrc = injuryImage.getAttribute("data-original-src") || injuryImage.src;
      loadImageToCanvas(originalImageSrc);
    } else {
      alert("Submit error: " + (out.error || out.message || "unknown"));
    }
  } catch (err) {
    console.error(err);
    alert("Network error.");
  }
});
