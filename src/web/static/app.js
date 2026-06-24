"use strict";

// Multi-sensor dataset viewer — vanilla JS, single page.
// Build marker: bumped each commit so users can verify their browser
// loaded the latest JS by checking the console message below.
const VIEWER_BUILD = "2026-06-24-rows";
console.log(`[viewer] app.js loaded — build ${VIEWER_BUILD}`);

const runSelect = document.getElementById("run-select");
const runStats = document.getElementById("run-stats");
const speedSelect = document.getElementById("speed-select");
const currentFrame = document.getElementById("current-frame");
const frameOverlay = document.getElementById("frame-overlay");
const scrubber = document.getElementById("scrubber");
const playBtn = document.getElementById("play-btn");
const timeReadout = document.getElementById("time-readout");
const metadataBlock = document.getElementById("metadata-block");

let state = {
  run: null,
  rows: [],
  idx: 0,
  playing: false,
  fps: 30,
  rafId: null,
  lastFrameAt: 0,
  // Leaflet
  map: null,
  trackLine: null,
  positionMarker: null,
  // Charts
  accelChart: null,
  gyroChart: null,
};

// ---- Utilities ----

function parseFloatSafe(value) {
  if (value === null || value === undefined || value === "" || value === "None") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function parseTimestamp(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (Number.isFinite(n)) return n;       // legacy float-epoch string
  const d = new Date(value);              // ISO 8601 string
  return Number.isFinite(d.getTime()) ? d.getTime() / 1000 : null;
}

function formatSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return `${bytes.toFixed(i ? 1 : 0)} ${units[i]}`;
}

/**
 * Render a CSV timestamp (ISO 8601 UTC, or legacy float epoch) as local-time
 * in YYYY-MM-DD HH:MM:SS.mmm. Browser's local time zone is used implicitly.
 */
function formatLocalTime(value) {
  if (value === null || value === undefined || value === "") return "N/A";
  let d;
  const n = Number(value);
  if (Number.isFinite(n)) {
    d = new Date(n * 1000);
  } else {
    d = new Date(value);
  }
  if (isNaN(d.getTime())) return String(value);
  const pad = (n, w = 2) => String(n).padStart(w, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` +
         `.${pad(d.getMilliseconds(), 3)}`;
}

// ---- Initialisation ----

async function init() {
  console.log("[viewer] init() starting");
  initMap();
  initCharts();

  // Bind review-mode listeners *unconditionally*. If the page first loaded
  // with zero recordings and a fresh run later finishes via the polling
  // refresh, these handlers still need to fire — they were being skipped
  // before because the early return below bypassed the bind step.
  runSelect.addEventListener("change", () => loadRun(runSelect.value));
  scrubber.addEventListener("input", onScrub);
  playBtn.addEventListener("click", togglePlay);
  console.log("[viewer] play/scrubber/runSelect handlers bound");

  const res = await fetch("/api/runs");
  const { runs } = await res.json();

  runSelect.innerHTML = "";
  if (!runs.length) {
    const opt = document.createElement("option");
    opt.textContent = "(no recordings found)";
    runSelect.appendChild(opt);
    return;
  }

  for (const run of runs) {
    const opt = document.createElement("option");
    opt.value = run.name;
    opt.textContent = `${run.name} (${formatSize(run.size_bytes)})`;
    runSelect.appendChild(opt);
  }

  loadRun(runs[0].name);
}

function initMap() {
  state.map = L.map("map").setView([0, 0], 2);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors",
  }).addTo(state.map);
}

function initCharts() {
  const chartOpts = {
    type: "line",
    options: {
      animation: false,
      maintainAspectRatio: false,
      responsive: true,
      plugins: { legend: { labels: { color: "#e6e6e6", boxWidth: 12 } } },
      scales: {
        x: { type: "linear", ticks: { color: "#8a98ab" }, grid: { color: "#2a3445" } },
        y: { ticks: { color: "#8a98ab" }, grid: { color: "#2a3445" } },
      },
      elements: { point: { radius: 0 }, line: { borderWidth: 1.5 } },
    },
  };
  state.accelChart = new Chart(document.getElementById("accel-chart"), {
    ...chartOpts,
    data: { datasets: [
      { label: "ax", data: [], borderColor: "#ff6e6e" },
      { label: "ay", data: [], borderColor: "#6cd66c" },
      { label: "az", data: [], borderColor: "#4ea1ff" },
      { label: "now", data: [], borderColor: "#ffb44e", borderDash: [4, 4], showLine: true },
    ]},
  });
  state.gyroChart = new Chart(document.getElementById("gyro-chart"), {
    ...chartOpts,
    data: { datasets: [
      { label: "gx", data: [], borderColor: "#ff6e6e" },
      { label: "gy", data: [], borderColor: "#6cd66c" },
      { label: "gz", data: [], borderColor: "#4ea1ff" },
      { label: "now", data: [], borderColor: "#ffb44e", borderDash: [4, 4], showLine: true },
    ]},
  });
}

// ---- Data loading ----

async function loadRun(runName) {
  stopPlay();
  state.run = runName;
  state.rows = [];
  state.idx = 0;

  // Metadata
  try {
    const md = await fetch(`/api/runs/${encodeURIComponent(runName)}/metadata`).then(r => r.json());
    metadataBlock.textContent = JSON.stringify(md, null, 2);
    const camFps = md?.sensor_configuration?.camera?.fps;
    if (Number.isFinite(camFps) && camFps > 0) state.fps = camFps;
  } catch {
    metadataBlock.textContent = "(no metadata)";
  }

  // Fetch every row of the dataset. We need them all for the scrubber + frame
  // playback. Sub-sampling for chart performance happens client-side in
  // fillCharts() — the per-frame index has to be unbroken or the scrubber
  // skips frames.
  const data = await fetch(`/api/runs/${encodeURIComponent(runName)}/data`).then(r => r.json());

  state.rows = data.rows;
  runStats.textContent = `${data.count} rows — ~${state.fps.toFixed(1)} fps`;
  console.log(`[viewer] loadRun ${runName}: ${data.count} rows loaded`);
  scrubber.max = String(Math.max(0, state.rows.length - 1));
  scrubber.value = "0";

  drawTrack();
  fillCharts();
  applyIndex(0);
}

function drawTrack() {
  if (state.trackLine) state.trackLine.remove();
  if (state.positionMarker) state.positionMarker.remove();

  const points = [];
  for (const r of state.rows) {
    const lat = parseFloatSafe(r.latitude);
    const lon = parseFloatSafe(r.longitude);
    if (lat !== null && lon !== null) points.push([lat, lon]);
  }
  if (!points.length) {
    state.map.setView([0, 0], 2);
    return;
  }
  state.trackLine = L.polyline(points, { color: "#4ea1ff", weight: 3 }).addTo(state.map);
  state.positionMarker = L.circleMarker(points[0], {
    color: "#ffb44e", fillColor: "#ffb44e", fillOpacity: 0.9, radius: 6,
  }).addTo(state.map);
  state.map.fitBounds(state.trackLine.getBounds(), { padding: [20, 20] });
}

function fillCharts() {
  // Sub-sample for charts only — playback still uses the full state.rows.
  // Chart.js stays snappy at <= ~5000 points; above that it gets sluggish on
  // weaker devices.
  const CHART_CAP = 5000;
  const chartStride = Math.max(1, Math.ceil(state.rows.length / CHART_CAP));
  const sampled = chartStride === 1
    ? state.rows
    : state.rows.filter((_, i) => i % chartStride === 0);

  const t0 = parseTimestamp(sampled[0]?.timestamp) ?? 0;
  const xs = sampled.map(r => (parseTimestamp(r.timestamp) ?? t0) - t0);
  const series = (key) => sampled.map((r, i) => ({ x: xs[i], y: parseFloatSafe(r[key]) }));

  state.accelChart.data.datasets[0].data = series("ax");
  state.accelChart.data.datasets[1].data = series("ay");
  state.accelChart.data.datasets[2].data = series("az");
  state.accelChart.update();

  state.gyroChart.data.datasets[0].data = series("gx");
  state.gyroChart.data.datasets[1].data = series("gy");
  state.gyroChart.data.datasets[2].data = series("gz");
  state.gyroChart.update();
}

// ---- Index / playback ----

function applyIndex(i) {
  if (!state.rows.length) return;
  state.idx = Math.max(0, Math.min(state.rows.length - 1, i));
  const r = state.rows[state.idx];

  // Frame image
  const filename = (r.image_path || "").split(/[\\/]/).pop();
  if (filename) {
    currentFrame.src = `/api/runs/${encodeURIComponent(state.run)}/images/${encodeURIComponent(filename)}`;
  } else {
    currentFrame.removeAttribute("src");
  }

  // Overlay
  const lat = parseFloatSafe(r.latitude);
  const lon = parseFloatSafe(r.longitude);
  const ax = parseFloatSafe(r.ax), ay = parseFloatSafe(r.ay), az = parseFloatSafe(r.az);
  const gx = parseFloatSafe(r.gx), gy = parseFloatSafe(r.gy), gz = parseFloatSafe(r.gz);
  const lines = [
    `t = ${formatLocalTime(r.timestamp)}`,
    lat !== null && lon !== null ? `gps = ${lat.toFixed(6)}, ${lon.toFixed(6)}` : "gps = (no fix)",
    ax !== null ? `a   = ${fmt(ax)} ${fmt(ay)} ${fmt(az)} m/s²` : "a   = N/A",
    gx !== null ? `w   = ${fmt(gx)} ${fmt(gy)} ${fmt(gz)} deg/s` : "w   = N/A",
  ];
  frameOverlay.textContent = lines.join("\n");

  // Map marker
  if (state.positionMarker && lat !== null && lon !== null) {
    state.positionMarker.setLatLng([lat, lon]);
  }

  // Vertical "now" line on the charts
  const t0 = parseTimestamp(state.rows[0]?.timestamp) ?? 0;
  const tNow = (parseTimestamp(r.timestamp) ?? t0) - t0;
  const updateNow = (chart, key) => {
    const yMin = chart.scales.y.min ?? -10;
    const yMax = chart.scales.y.max ?? 10;
    const ds = chart.data.datasets[3];
    ds.data = [{ x: tNow, y: yMin }, { x: tNow, y: yMax }];
    chart.update("none");
  };
  updateNow(state.accelChart);
  updateNow(state.gyroChart);

  // Scrubber + readout
  scrubber.value = String(state.idx);
  const total = state.rows.length;
  timeReadout.textContent = `${state.idx + 1} / ${total}   t = ${formatLocalTime(r.timestamp)}`;
}

function fmt(v) {
  const s = (v >= 0 ? "+" : "") + v.toFixed(2);
  return s.padStart(7, " ");
}

function onScrub() {
  stopPlay();
  applyIndex(Number(scrubber.value));
}

function togglePlay() {
  console.log(`[viewer] play click — rows=${state.rows.length}, playing=${state.playing}, fps=${state.fps}, run=${state.run}`);
  if (state.playing) stopPlay();
  else startPlay();
}

function startPlay() {
  if (!state.rows.length) {
    console.warn("[viewer] startPlay: no rows loaded — nothing to play");
    return;
  }
  const speed = Number(speedSelect?.value) || 1;
  // Effective per-frame interval. Floor at 10 ms (~100 fps display max) so
  // pathological speed × fps combinations don't lock the loop, but otherwise
  // honour what the user asked for — a 30-min recording at 8× plays in ~4 min
  // as expected.
  const period = Math.max(10, 1000 / Math.max(1, state.fps * speed));
  const totalSec = (state.rows.length * period) / 1000;
  console.log(`[viewer] startPlay: ${state.rows.length} frames @ ${state.fps} fps, speed=${speed}×, period=${period.toFixed(1)} ms (≈${totalSec.toFixed(1)}s playback)`);
  state.playing = true;
  playBtn.textContent = "❚❚ Pause";
  state.lastFrameAt = performance.now();
  const tick = (now) => {
    if (!state.playing) return;
    if (now - state.lastFrameAt >= period) {
      const next = state.idx + 1;
      if (next >= state.rows.length) {
        stopPlay();
        return;
      }
      applyIndex(next);
      state.lastFrameAt = now;
    }
    state.rafId = requestAnimationFrame(tick);
  };
  state.rafId = requestAnimationFrame(tick);
}

function stopPlay() {
  state.playing = false;
  playBtn.textContent = "▶ Play";
  if (state.rafId) cancelAnimationFrame(state.rafId);
  state.rafId = null;
}

// ---- Recording control ----

const recordForm = document.getElementById("record-form");
const recordLive = document.getElementById("record-live");
const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const recordError = document.getElementById("record-error");
const liveName = document.getElementById("live-name");
const liveElapsed = document.getElementById("live-elapsed");
const liveFrames = document.getElementById("live-frames");
const liveRecords = document.getElementById("live-records");
const liveTargetFps = document.getElementById("live-target-fps");
const liveBar = document.getElementById("live-bar");
const liveLogBlock = document.getElementById("live-log-block");
const liveGps = document.getElementById("live-gps");
const liveAccel = document.getElementById("live-accel");
const liveGyro = document.getElementById("live-gyro");
const fpsSlider = document.getElementById("opt-fps");
const fpsOut = document.getElementById("opt-fps-out");

let pollHandle = null;
let liveMarker = null;     // Leaflet marker showing current GPS position during recording
let liveStartedAt = null;  // Date used to back-compute elapsed time before the first log line

// Rolling buffer of IMU samples for the live chart while recording.
// 60 samples × 1 Hz poll = a 60-second window of live history.
const LIVE_BUFFER_SIZE = 60;
const liveBuffer = { t: [], ax: [], ay: [], az: [], gx: [], gy: [], gz: [] };
let lastLiveTs = null;

function resetLiveBuffer() {
  for (const k of Object.keys(liveBuffer)) liveBuffer[k].length = 0;
  lastLiveTs = null;
}

fpsSlider.addEventListener("input", () => { fpsOut.textContent = fpsSlider.value; });

document.querySelectorAll(".dur-preset").forEach((b) => {
  b.addEventListener("click", () => {
    document.getElementById("opt-duration").value = b.dataset.secs;
  });
});

function showError(msg) {
  recordError.textContent = msg || "";
  recordError.hidden = !msg;
}

function collectOpts() {
  return {
    real_camera: document.getElementById("opt-real-camera").checked,
    real_gps:    document.getElementById("opt-real-gps").checked,
    enable_imu:  document.getElementById("opt-enable-imu").checked,
    real_imu:    document.getElementById("opt-real-imu").checked,
    fps:         Number(fpsSlider.value),
    duration:    Number(document.getElementById("opt-duration").value),
    output_name: document.getElementById("opt-output-name").value.trim(),
  };
}

function formatElapsed(secs) {
  secs = Math.max(0, Math.round(secs));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function renderStatus(s) {
  if (s.running && s.state) {
    document.body.classList.add("recording");
    recordForm.hidden = true;
    recordLive.hidden = false;
    liveName.textContent = s.state.output_name || "";
    const params = s.state.params || {};
    liveTargetFps.textContent = params.fps ?? "—";

    // Track the recording's start time so we can show elapsed seconds
    // even before main.py's first "[X.Xs] Frames: N" log line arrives.
    if (s.state.started_at) {
      liveStartedAt = new Date(s.state.started_at);
    }

    const fallbackElapsed = liveStartedAt
      ? (Date.now() - liveStartedAt.getTime()) / 1000
      : 0;
    const elapsed = s.progress?.elapsed_s ?? fallbackElapsed;
    const frames  = s.progress?.frames    ?? 0;
    const records = s.progress?.records   ?? 0;
    liveElapsed.textContent = formatElapsed(elapsed);
    liveFrames.textContent  = frames.toLocaleString();
    liveRecords.textContent = records.toLocaleString();

    const duration = params.duration || 0;
    if (duration > 0) {
      const pct = Math.min(100, (elapsed / duration) * 100);
      liveBar.style.width = `${pct}%`;
    } else {
      liveBar.style.width = "0%";
    }

    liveLogBlock.textContent = (s.log_tail || []).join("\n");
    updateLivePreview();
  } else {
    document.body.classList.remove("recording");
    recordForm.hidden = false;
    recordLive.hidden = true;
    liveStartedAt = null;
    // Tear down any live preview state from the previous recording.
    if (liveMarker) {
      try { liveMarker.remove(); } catch {}
      liveMarker = null;
    }
    resetLiveBuffer();
  }
}

/**
 * Fetch the most recent JPEG + CSV row from the live recording and reflect them
 * in the existing Frame and GPS Track panels so they double as a live preview
 * while a recording is in progress.
 */
async function updateLivePreview() {
  // Latest frame — cache-bust so the browser re-requests every poll.
  if (currentFrame) {
    currentFrame.src = `/api/recording/latest_frame?t=${Date.now()}`;
    currentFrame.onerror = () => { currentFrame.removeAttribute("src"); };
  }

  // Latest CSV row — drives the GPS marker + IMU readouts + frame overlay.
  try {
    const r = await fetch("/api/recording/latest_row").then(x => x.json());
    const row = r?.row;
    if (!row) {
      liveGps.textContent = "—";
      liveAccel.textContent = "—";
      liveGyro.textContent = "—";
      return;
    }

    const lat = parseFloatSafe(row.latitude);
    const lon = parseFloatSafe(row.longitude);
    const ax = parseFloatSafe(row.ax);
    const ay = parseFloatSafe(row.ay);
    const az = parseFloatSafe(row.az);
    const gx = parseFloatSafe(row.gx);
    const gy = parseFloatSafe(row.gy);
    const gz = parseFloatSafe(row.gz);

    liveGps.textContent = (lat !== null && lon !== null)
      ? `${lat.toFixed(6)}, ${lon.toFixed(6)}`
      : "(no fix)";
    liveAccel.textContent = (ax !== null)
      ? `${fmtSigned(ax)} ${fmtSigned(ay)} ${fmtSigned(az)}`
      : "—";
    liveGyro.textContent = (gx !== null)
      ? `${fmtSigned(gx)} ${fmtSigned(gy)} ${fmtSigned(gz)}`
      : "—";

    // Move (or create) the GPS marker on the map.
    if (lat !== null && lon !== null && state.map) {
      if (!liveMarker) {
        liveMarker = L.circleMarker([lat, lon], {
          color: "#ff5050", fillColor: "#ff5050", fillOpacity: 0.9, radius: 7,
        }).addTo(state.map);
        state.map.setView([lat, lon], 16);
      } else {
        liveMarker.setLatLng([lat, lon]);
      }
    }

    // Append IMU samples to the rolling buffer and update the live charts.
    const ts = parseTimestamp(row.timestamp);
    if (ts !== null && ts !== lastLiveTs && ax !== null && gx !== null) {
      lastLiveTs = ts;
      liveBuffer.t.push(ts);
      liveBuffer.ax.push(ax); liveBuffer.ay.push(ay); liveBuffer.az.push(az);
      liveBuffer.gx.push(gx); liveBuffer.gy.push(gy); liveBuffer.gz.push(gz);
      if (liveBuffer.t.length > LIVE_BUFFER_SIZE) {
        const trim = liveBuffer.t.length - LIVE_BUFFER_SIZE;
        for (const k of Object.keys(liveBuffer)) liveBuffer[k].splice(0, trim);
      }
      updateLiveCharts();
    }

    // Update the frame overlay even though we don't have the full
    // synchronized record — what we have is good enough for live preview.
    if (frameOverlay) {
      const lines = [
        `t = ${formatLocalTime(row.timestamp)}`,
        liveGps.textContent !== "—" ? `gps = ${liveGps.textContent}` : "gps = (no fix)",
        liveAccel.textContent !== "—" ? `a   = ${liveAccel.textContent} m/s²` : "a   = N/A",
        liveGyro.textContent !== "—"  ? `w   = ${liveGyro.textContent} deg/s` : "w   = N/A",
      ];
      frameOverlay.textContent = lines.join("\n");
    }
  } catch {
    // Network blip during recording — silently ignore; next tick will retry.
  }
}

function fmtSigned(v) {
  const s = (v >= 0 ? "+" : "") + v.toFixed(2);
  return s.padStart(7, " ");
}

function updateLiveCharts() {
  if (!state.accelChart || !liveBuffer.t.length) return;
  const t0 = liveBuffer.t[0];
  const xs = liveBuffer.t.map(t => t - t0);
  const series = (key) => xs.map((x, i) => ({ x, y: liveBuffer[key][i] }));

  state.accelChart.data.datasets[0].data = series("ax");
  state.accelChart.data.datasets[1].data = series("ay");
  state.accelChart.data.datasets[2].data = series("az");
  state.accelChart.data.datasets[3].data = [];  // hide review-mode "now" line
  state.accelChart.update("none");

  state.gyroChart.data.datasets[0].data = series("gx");
  state.gyroChart.data.datasets[1].data = series("gy");
  state.gyroChart.data.datasets[2].data = series("gz");
  state.gyroChart.data.datasets[3].data = [];
  state.gyroChart.update("none");
}

async function pollStatus() {
  try {
    const resp = await fetch("/api/recording/status");
    const s = await resp.json();
    renderStatus(s);
    if (!s.running && pollHandle) {
      clearInterval(pollHandle);
      pollHandle = null;
      // Recording just finished — refresh the run dropdown so the new dataset shows up.
      const list = await fetch("/api/runs").then(r => r.json());
      runSelect.innerHTML = "";
      for (const r of list.runs) {
        const opt = document.createElement("option");
        opt.value = r.name;
        opt.textContent = `${r.name} (${formatSize(r.size_bytes)})`;
        runSelect.appendChild(opt);
      }
      // Auto-select the most recently finished recording if there is one.
      if (list.runs.length) {
        runSelect.value = list.runs[list.runs.length - 1].name;
        loadRun(runSelect.value);
      }
    }
  } catch (e) {
    console.error("status poll failed", e);
  }
}

function startPolling() {
  if (pollHandle) return;
  pollStatus();
  pollHandle = setInterval(pollStatus, 1000);
}

startBtn.addEventListener("click", async () => {
  showError(null);
  const opts = collectOpts();
  try {
    const resp = await fetch("/api/recording/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      showError(err.detail || `failed: HTTP ${resp.status}`);
      return;
    }
    startPolling();
  } catch (e) {
    showError(`network error: ${e.message}`);
  }
});

stopBtn.addEventListener("click", async () => {
  showError(null);
  stopBtn.disabled = true;
  try {
    const resp = await fetch("/api/recording/stop", { method: "POST" });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      showError(err.detail || `failed: HTTP ${resp.status}`);
    }
  } catch (e) {
    showError(`network error: ${e.message}`);
  } finally {
    setTimeout(() => { stopBtn.disabled = false; }, 1500);
  }
});

// Re-attach to a recording if one was already running when the page loaded.
pollStatus().then(() => {
  if (recordLive && !recordLive.hidden) startPolling();
});

init().catch((e) => {
  console.error(e);
  metadataBlock.textContent = `init error: ${e.message}`;
});
