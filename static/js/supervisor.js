// textarea autoresize
function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

// ===== CONFIG (per-user localStorage) =====
const FORM_ID = "pcrForm";
const SCHEMA_VER = "v1"; // bump when schema changes

// Get user id injected by server (prefer window.APP, fallback to data-user-id)
const USER_ID =
  (window.APP && window.APP.userId) ||
  document.documentElement.getAttribute("data-user-id") ||
  "anon";

// one key per user
const LS_PREFIX = `PCRForm:${SCHEMA_VER}:user:`;
const STORAGE_KEY = `${LS_PREFIX}${USER_ID}`;
const AUTOSAVE_MS = 300; // debounce delay

// ===== contenteditable cell ids (MAKE SURE THESE ARE UNIQUE IN HTML) =====
const CE_IDS = [
  "time1","time2","time3","time4","time5","time6",
  "pulse1","pulse2","pulse3","pulse4","pulse5","pulse6",
  "resp1","resp2","resp3","resp4","resp5","resp6",
  "bp1","bp2","bp3","bp4","bp5","bp6",
  "loc1","loc2","loc3","loc4","loc5","loc6",
  "skin1","skin2","skin3","skin4","skin5","skin6",
  "spo21","spo22","spo23","spo24","spo25","spo26"
  // add any renamed/second-table IDs here (e.g., "v2_time1", ...)
];

// ===== State =====
const form = document.getElementById(FORM_ID);
const canvas = document.getElementById("injuryCanvas");
const ctx = canvas.getContext("2d");
const injuryImage = document.getElementById("injuryImage");
const resetImageBtn = document.getElementById("resetImageBtn");

let injuryPoints = []; // [{x,y}, ...]
let saveTimer;

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

  // (optional but useful) stamp user_id so you can debug
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

// Debounced autosave to this user's key
function autosave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(serializeForm(form)));
  }, AUTOSAVE_MS);
}

// ===== Init once DOM is ready =====
document.addEventListener("DOMContentLoaded", () => {
  // 0) Ensure per-user isolation: remove other users' keys with the same prefix
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const k = localStorage.key(i);
    if (k && k.startsWith(LS_PREFIX) && k !== STORAGE_KEY) {
      localStorage.removeItem(k);
    }
  }

  // 1) draw the base image
  const originalImageSrc = injuryImage.getAttribute("data-original-src") || injuryImage.src;
  loadImageToCanvas(originalImageSrc);

  // 2) restore from this user's localStorage only
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw) {
    try {
      const data = JSON.parse(raw);
      loadImageToCanvas(originalImageSrc, () => {
        restoreForm(form, data);
      });
    } catch {}
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

  // 7) page hide/unload: best-effort save (to this user's key)
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(serializeForm(form)));
    }
  });
  window.addEventListener("beforeunload", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(serializeForm(form)));
  });
});

// ===== Submit (clear this user's storage on success) =====
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
      // delete ONLY this user's entry
      localStorage.removeItem(STORAGE_KEY);
      alert("Submitted!");
    } else {
      alert("Submit error: " + (out.error || out.message || "unknown"));
    }
  } catch (err) {
    console.error(err);
    alert("Network error.");
  }
});
