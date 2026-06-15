"use strict";

// Multi-sensor dataset viewer — vanilla JS, single page.

const runSelect = document.getElementById("run-select");
const runStats = document.getElementById("run-stats");
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

// ---- Initialisation ----

async function init() {
  initMap();
  initCharts();

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
  runSelect.addEventListener("change", () => loadRun(runSelect.value));
  scrubber.addEventListener("input", onScrub);
  playBtn.addEventListener("click", togglePlay);

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

  // CSV rows (sub-sample very large datasets to keep the UI responsive)
  const probe = await fetch(`/api/runs/${encodeURIComponent(runName)}/data?stride=1000`).then(r => r.json());
  const stride = probe.count > 5000 ? Math.ceil(probe.count / 5000) : 1;
  const data = stride === 1
    ? probe
    : await fetch(`/api/runs/${encodeURIComponent(runName)}/data?stride=${stride}`).then(r => r.json());

  state.rows = data.rows;
  runStats.textContent = `${data.count} rows (stride ${data.stride}) — ~${state.fps.toFixed(1)} fps`;
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
  const t0 = parseTimestamp(state.rows[0]?.timestamp) ?? 0;
  const xs = state.rows.map(r => (parseTimestamp(r.timestamp) ?? t0) - t0);
  const series = (key) => state.rows.map((r, i) => ({ x: xs[i], y: parseFloatSafe(r[key]) }));

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
    `t = ${r.timestamp || "N/A"}`,
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
  timeReadout.textContent = `${state.idx + 1} / ${total}   t = ${r.timestamp || "?"}`;
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
  if (state.playing) stopPlay();
  else startPlay();
}

function startPlay() {
  if (!state.rows.length) return;
  state.playing = true;
  playBtn.textContent = "❚❚ Pause";
  state.lastFrameAt = performance.now();
  const period = 1000 / Math.max(1, state.fps);
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

init().catch((e) => {
  console.error(e);
  metadataBlock.textContent = `init error: ${e.message}`;
});
