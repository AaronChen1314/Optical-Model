const state = {
  materials: [],
  templates: [],
  layers: [],
  method: "tmm",
  periodic: false,
  compareType: "tmm_flat_vs_rcwa_flat",
  result: null,
  compare: null,
  temperatureResult: null,
  thicknessResult: null,
  bandgapModels: [],
  chartMode: "absorption",
  nkDisplayMode: "n",
};

const APP_VERSION = "optics-app-2026-06-05-chart-5";
const colors = ["#1f7a5c", "#286f9e", "#b7851d", "#b64b5e", "#6f5aa7", "#6a7d39", "#9a5b28", "#4d7480"];
const text = {
  ready: "\u51c6\u5907\u5c31\u7eea",
  materialLoaded: "\u79cd\u5185\u7f6e\u6750\u6599\u5df2\u52a0\u8f7d",
  submit: "\u63d0\u4ea4\u8ba1\u7b97",
  tmmDone: "TMM \u8ba1\u7b97\u5b8c\u6210",
  tempRun: "\u8fd0\u884c\u6e29\u5ea6\u626b\u63cf",
  tempDone: "\u6e29\u5ea6\u626b\u63cf\u5b8c\u6210",
  noJsc: "\u6682\u65e0\u5149\u7535\u6d41\u7ed3\u679c",
  wait: "\u7b49\u5f85\u8ba1\u7b97\u7ed3\u679c",
  noPlotly: "Plotly CDN \u672a\u52a0\u8f7d\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u6216\u672c\u5730\u9759\u6001\u8d44\u6e90\u3002",
  saved: "\u9879\u76ee\u5df2\u4fdd\u5b58\u5230\u6d4f\u89c8\u5668\u672c\u5730",
  restored: "\u5df2\u6062\u590d\u4e0a\u6b21\u9879\u76ee",
  imported: "\u9879\u76ee\u5bfc\u5165\u5b8c\u6210",
  noExport: "\u6ca1\u6709\u53ef\u5bfc\u51fa\u7684\u7ed3\u679c",
};

function $(id) {
  return document.getElementById(id);
}

async function init() {
  if (window.lucide) lucide.createIcons();
  bindEvents();
  const meta = await api("/api/materials");
  state.materials = meta.materials;
  state.templates = meta.templates;
  $("materialCount").textContent = `${state.materials.length} ${text.materialLoaded}`;
  renderTemplateOptions();
  loadTemplate("all_perovskite_planar_reference");
  restoreProject();
  updateMethodControls();
  renderLayers();
  renderChart();
}

function bindEvents() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => setTab(button.dataset.tab));
  });
  document.querySelectorAll(".segment").forEach((button) => {
    button.addEventListener("click", () => setMethod(button.dataset.method));
  });
  document.querySelectorAll(".choice").forEach((button) => {
    button.addEventListener("click", () => setPeriodic(button.dataset.periodic === "true"));
  });
  $("compareType").addEventListener("change", (event) => {
    state.compareType = event.target.value;
    updateMethodControls();
  });
  $("templateSelect").addEventListener("change", (event) => loadTemplate(event.target.value));
  $("tempRef").addEventListener("change", () => {
    state.bandgapModels = state.bandgapModels.map((model) => ({ ...model, reference_K: Number($("tempRef").value) }));
  });
  $("addLayerBtn").addEventListener("click", addLayer);
  $("runBtn").addEventListener("click", runSimulation);
  $("tempBtn").addEventListener("click", runTemperatureSweep);
  $("thicknessBtn").addEventListener("click", runThicknessSweep);
  $("csvBtn").addEventListener("click", exportCsv);
  $("chartMode").addEventListener("change", (event) => {
    state.chartMode = event.target.value;
    updateChartControls();
    renderChart();
  });
  $("nkDisplayMode").addEventListener("change", (event) => {
    state.nkDisplayMode = event.target.value;
    renderChart();
  });
  $("pngBtn").addEventListener("click", () => exportChart("png"));
  $("svgBtn").addEventListener("click", () => exportChart("svg"));
  $("pdfBtn").addEventListener("click", exportChartPdf);
  $("saveProjectBtn").addEventListener("click", () => saveProject(true));
  $("exportProjectBtn").addEventListener("click", exportProject);
  $("importProjectInput").addEventListener("change", importProject);
  $("materialInput").addEventListener("change", validateMaterial);
}

function setTab(tab) {
  document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((item) => item.classList.toggle("active", item.dataset.panel === tab));
}

function setMethod(method) {
  state.method = method;
  document.querySelectorAll(".segment").forEach((item) => item.classList.toggle("active", item.dataset.method === method));
  updateMethodControls();
}

function setPeriodic(periodic) {
  state.periodic = periodic;
  document.querySelectorAll(".choice").forEach((item) => item.classList.toggle("active", item.dataset.periodic === String(periodic)));
  updateMethodControls();
}

function updateMethodControls() {
  const isTmm = state.method === "tmm";
  const isCompare = state.method === "compare";
  const comparePeriodic = isCompare && state.compareType === "rcwa_flat_vs_periodic";
  const showRcwa = state.method === "rcwa" || comparePeriodic;
  const showPeriodicFields = showRcwa && (state.method === "rcwa" ? state.periodic : true);
  $("compareControls").classList.toggle("hidden", !isCompare);
  $("rcwaControls").classList.toggle("hidden", isTmm || (isCompare && state.compareType === "tmm_flat_vs_rcwa_flat"));
  $("periodicFields").classList.toggle("hidden", !showPeriodicFields);
  document.querySelector(".inline-choice").classList.toggle("hidden", isCompare);
  if ($("compareType")) $("compareType").value = state.compareType;
}

function renderTemplateOptions() {
  $("templateSelect").innerHTML = state.templates.map((template) => `<option value="${template.id}">${escapeHtml(template.name)}</option>`).join("");
}

function loadTemplate(templateId) {
  const template = state.templates.find((item) => item.id === templateId) || state.templates[0];
  if (!template) return;
  state.layers = structuredClone(template.layers);
  $("templateSelect").value = template.id;
  syncRcwaFromLayers();
  syncBandgapModels();
  renderBandgapEditor();
  renderThicknessEditor();
  renderLayers();
}

function renderLayers() {
  const options = state.materials.map((m) => `<option value="${escapeAttr(m.id)}">${escapeHtml(m.name)}</option>`).join("");
  $("layerEditor").innerHTML = state.layers.map((layer, index) => `
    <div class="layer-row" data-index="${index}">
      <input value="${escapeAttr(layer.name)}" aria-label="layer name" data-field="name">
      <select data-field="material">${options}</select>
      <input value="${escapeAttr(layer.thickness_nm)}" aria-label="thickness" data-field="thickness_nm">
      <label class="toggle" title="active layer"><input type="checkbox" data-field="active" ${layer.active ? "checked" : ""}></label>
      <button class="square-btn" title="delete layer" data-action="delete"><i data-lucide="trash-2"></i></button>
    </div>
  `).join("");
  document.querySelectorAll(".layer-row").forEach((row) => {
    const index = Number(row.dataset.index);
    const materialSelect = row.querySelector('select[data-field="material"]');
    materialSelect.value = state.layers[index].material;
    row.querySelectorAll("input, select").forEach((input) => {
      input.addEventListener("change", () => updateLayer(index, input.dataset.field, input.type === "checkbox" ? input.checked : input.value));
    });
    row.querySelector('[data-action="delete"]').addEventListener("click", () => {
      state.layers.splice(index, 1);
      renderLayers();
    });
  });
  if (window.lucide) lucide.createIcons();
  syncBandgapModels();
  renderBandgapEditor();
  renderThicknessEditor();
}

function updateLayer(index, field, value) {
  state.layers[index][field] = value;
  syncRcwaFromLayers();
  syncBandgapModels();
  renderBandgapEditor();
  renderThicknessEditor();
}

function addLayer() {
  const insertAt = Math.max(1, state.layers.length - 1);
  state.layers.splice(insertAt, 0, { name: "New layer", material: "ito", thickness_nm: 50, active: false, coherent: true, n_source: "database" });
  renderLayers();
}

function activeLayers() {
  return state.layers
    .map((layer, index) => ({ ...layer, layer_index: index }))
    .filter((layer) => layer.active);
}

function syncBandgapModels() {
  const existing = new Map(state.bandgapModels.map((item) => [`${item.layer_name}|${item.material}`, item]));
  state.bandgapModels = activeLayers().map((layer) => {
    const key = `${layer.name}|${layer.material}`;
    if (existing.has(key)) return existing.get(key);
    return {
      layer_name: layer.name,
      material: layer.material,
      ...defaultBandgapForLayer(layer),
      reference_K: Number($("tempRef")?.value || 300),
    };
  });
}

function defaultBandgapForLayer(layer) {
  const template = $("templateSelect")?.value || "all_perovskite_planar_reference";
  if (template === "perovskite_silicon") {
    if (layer.material === "si_crystalline") return { Eg_ref_eV: 1.124, alpha_eV_per_K: -2.68e-4 };
    return { Eg_ref_eV: 1.650, alpha_eV_per_K: 5.95e-4 };
  }
  if (String(layer.name).toLowerCase().includes("nbg") || layer.material === "nbg_perovskite") {
    return { Eg_ref_eV: 1.25, alpha_eV_per_K: -2.5e-4 };
  }
  return { Eg_ref_eV: 1.75, alpha_eV_per_K: -2.5e-4 };
}

function renderBandgapEditor() {
  const editor = $("bandgapEditor");
  if (!editor) return;
  editor.innerHTML = state.bandgapModels.map((model, index) => `
    <div class="mini-row three" data-index="${index}">
      <span title="${escapeAttr(model.layer_name)}">${escapeHtml(model.layer_name)}</span>
      <input type="number" step="0.001" value="${model.Eg_ref_eV}" data-bg-field="Eg_ref_eV">
      <input type="number" step="0.00001" value="${model.alpha_eV_per_K}" data-bg-field="alpha_eV_per_K">
    </div>
  `).join("");
  editor.querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", () => {
      const row = input.closest(".mini-row");
      state.bandgapModels[Number(row.dataset.index)][input.dataset.bgField] = Number(input.value);
    });
  });
}

function renderThicknessEditor() {
  const editor = $("thicknessEditor");
  if (!editor) return;
  editor.innerHTML = activeLayers().map((layer) => {
    const base = Number(layer.thickness_nm) || 100;
    return `
      <div class="mini-row" data-layer-name="${escapeAttr(layer.name)}">
        <span title="${escapeAttr(layer.name)}">${escapeHtml(layer.name)}</span>
        <input type="number" value="${Math.max(1, base - 50)}" data-scan-field="start_nm">
        <input type="number" value="${base + 50}" data-scan-field="stop_nm">
        <input type="number" value="10" min="1" data-scan-field="step_nm">
      </div>
    `;
  }).join("");
}

function syncRcwaFromLayers() {
  const wbg = state.layers.find((layer) => layer.material === "wbg_perovskite" || layer.material === "perovskite_164");
  const nbg = state.layers.find((layer) => layer.material === "nbg_perovskite");
  if (wbg && Number.isFinite(Number(wbg.thickness_nm))) $("rcwaWbg").value = Number(wbg.thickness_nm);
  if (nbg && Number.isFinite(Number(nbg.thickness_nm))) $("rcwaNbg").value = Number(nbg.thickness_nm);
}

async function runSimulation() {
  setProgress(8, text.submit);
  const payload = buildPayload();
  try {
    if (state.method === "tmm") {
      const result = await api("/api/simulate/tmm", payload);
      state.result = result;
      state.compare = null;
      setProgress(100, text.tmmDone);
      renderMetrics(result);
      setResultChartMode("absorption");
      renderChart();
      saveProject(false);
    } else if (state.method === "rcwa") {
      const { job_id } = await api("/api/simulate/rcwa", payload);
      await pollJob(job_id, (job) => {
        state.result = job.result;
        state.compare = null;
      });
    } else {
      const compareStart = await api("/api/simulate/compare", payload);
      state.result = compareStart.tmm || null;
      renderMetrics(compareStart.tmm || null);
      renderModelTags(compareStart.tmm ? [compareStart.tmm] : []);
      renderChart();
      await pollJob(compareStart.job_id, (job) => {
        state.compare = job.result;
        state.result = job.result.rcwa_periodic || job.result.rcwa_flat || job.result.rcwa || null;
      });
    }
  } catch (error) {
    setProgress(0, error.message);
  }
}

async function runTemperatureSweep() {
  setProgress(8, text.tempRun);
  try {
    const result = await api("/api/temperature/sweep", buildPayload());
    state.temperatureResult = result;
    const last = result.runs[result.runs.length - 1];
    state.result = last ? last.result : null;
    state.compare = null;
    setProgress(100, text.tempDone);
    renderMetrics(state.result);
    setResultChartMode("temp_jsc");
    renderChart();
    saveProject(false);
  } catch (error) {
    setProgress(0, error.message);
  }
}

async function runThicknessSweep() {
  const periodicCost = state.method === "rcwa" && state.periodic || state.method === "compare" && state.compareType === "rcwa_flat_vs_periodic";
  setProgress(8, periodicCost ? "RCWA thickness sweep is not enabled by default because of computational cost. Running TMM planar scan." : "Running thickness scan");
  try {
    const payload = buildPayload();
    payload.rcwa = {};
    const result = await api("/api/thickness/sweep", payload);
    state.thicknessResult = result;
    state.compare = null;
    setProgress(100, "Thickness scan complete");
    setResultChartMode("thickness");
    renderChart();
    saveProject(false);
  } catch (error) {
    setProgress(0, error.message);
  }
}

async function pollJob(jobId, onComplete) {
  let done = false;
  while (!done) {
    await wait(1200);
    const job = await api(`/api/jobs/${jobId}`);
    setProgress(job.progress, job.message || job.status);
    if (job.status === "complete") {
      onComplete(job);
      renderMetrics(state.result);
      renderChart();
      saveProject(false);
      done = true;
    } else if (job.status === "error") {
      throw new Error(job.error || "Background job failed");
    }
  }
}

function buildPayload() {
  const usesPeriodicParams = state.method === "rcwa" && state.periodic || state.method === "compare" && state.compareType === "rcwa_flat_vs_periodic";
  const shape = usesPeriodicParams ? $("rcwaShape").value : "Planar";
  return {
    template_id: $("templateSelect").value,
    compare_type: state.compareType,
    layers: state.layers,
    wavelength: {
      start_nm: Number($("wlStart").value),
      stop_nm: Number($("wlStop").value),
      step_nm: Number($("wlStep").value),
    },
    rcwa: {
      periodic: usesPeriodicParams,
      shape,
      pitch: Number($("rcwaPitch").value),
      height: Number($("rcwaHeight").value),
      duty_cycle: Number($("rcwaDuty").value),
      nG: Number($("rcwaNG").value),
      slices: Number($("rcwaSlices").value),
      t_wbg: Number($("rcwaWbg").value),
      t_nbg: Number($("rcwaNbg").value),
    },
    temperature: {
      temperatures_K: $("tempList").value.split(",").map((item) => Number(item.trim())).filter(Number.isFinite),
      reference_K: Number($("tempRef").value),
      bandgap_models: state.bandgapModels.map((model) => ({ ...model, reference_K: Number($("tempRef").value) })),
    },
    thickness_scan: {
      layers: Array.from(document.querySelectorAll("#thicknessEditor .mini-row")).map((row) => {
        const item = { layer_name: row.dataset.layerName };
        row.querySelectorAll("input").forEach((input) => {
          item[input.dataset.scanField] = Number(input.value);
        });
        return item;
      }),
    },
  };
}

function renderMetrics(result) {
  const jsc = result ? result.jsc_mA_cm2 || {} : {};
  const entries = Object.entries(jsc);
  $("metrics").innerHTML = entries.length ? entries.map(([name, value]) => `
    <div class="metric"><strong>${Number(value).toFixed(3)}</strong><span>${escapeHtml(name)} mA/cm²</span></div>
  `).join("") : `<div class="metric"><strong>-</strong><span>${text.noJsc}</span></div>`;
}

function renderModelTags(results) {
  const tags = results.map(resultLabel).filter(Boolean);
  $("modelTags").innerHTML = tags.map((tag) => `<span class="model-tag">${escapeHtml(tag)}</span>`).join("");
}

function resultLabel(result) {
  if (!result) return "";
  const method = String(result.method || "").toUpperCase();
  const geometry = result.geometry || "planar";
  const shape = geometry === "periodic" ? `: ${result.shape || result.periodic_parameters?.shape || "Periodic"}` : "";
  return `${method} ${geometry}${shape}`;
}

function modelContext(result) {
  if (!result) return "";
  const label = resultLabel(result);
  if (state.chartMode === "temp_nk") {
    return `${label} - bandgap shift + smoothed long-wavelength tail + local KK correction`;
  }
  return label;
}

function renderChart() {
  updateChartControls();
  renderModelTags(state.compare ? Object.values(state.compare).filter((item) => item && typeof item === "object" && item.method) : (state.result ? [state.result] : []));
  if (state.chartMode.startsWith("temp_")) {
    renderTemperatureChart();
    return;
  }
  if (state.chartMode === "thickness") {
    renderThicknessChart();
    return;
  }
  if (state.compare) {
    renderCompareChart(state.compare);
    return;
  }
  if (!state.result) {
    drawPlot([], layout(text.wait));
    return;
  }
  drawPlot(tracesForResult(state.result), layout(titleForMode()));
}

function tracesForResult(result) {
  const wl = result.wavelength_nm || [];
  if (state.chartMode === "current") {
    const layerCurrents = result.layer_currents_mA_cm2 || result.jsc_mA_cm2 || {};
    const active = result.active_currents_mA_cm2 || {};
    const entries = Object.entries(layerCurrents).filter(([name]) => name !== "matched" && name !== "sum_active").sort((a, b) => Number(a[1]) - Number(b[1]));
    const traces = [{
      type: "bar",
      orientation: "h",
      x: entries.map(([, value]) => Number(value)),
      y: entries.map(([name]) => name),
      text: entries.map(([, value]) => `${Number(value).toFixed(3)} mA/cm²`),
      textposition: "outside",
      cliponaxis: false,
      marker: { color: entries.map(([name], index) => active[name] !== undefined ? "#1f7a5c" : colors[(index + 2) % colors.length]) },
      name: "Layer equivalent photocurrent",
    }];
    const matched = Number(result.matched_current_mA_cm2 ?? result.jsc_mA_cm2?.matched);
    if (Number.isFinite(matched) && entries.length) {
      traces.push({
        type: "scatter",
        mode: "lines",
        x: [matched, matched],
        y: [entries[0][0], entries[entries.length - 1][0]],
        name: "matched current",
        line: { color: "#b64b5e", width: 3, dash: "dash" },
        hovertemplate: `matched ${matched.toFixed(3)} mA/cm²<extra></extra>`,
      });
    }
    return traces;
  }
  if (state.chartMode === "reflection") {
    const traces = [{ x: wl, y: result.reflection || [], type: "scatter", mode: "lines", name: "R", line: { color: "#b64b5e", width: 2 } }];
    if (result.transmission) traces.push({ x: wl, y: result.transmission, type: "scatter", mode: "lines", name: "T", line: { color: "#286f9e", width: 2 } });
    return traces;
  }
  return (result.layers || []).filter((layer) => layer.absorption).map((layer, index) => ({
    x: wl,
    y: layer.absorption,
    type: "scatter",
    mode: "lines",
    name: layer.name || layer.material,
    visible: layer.active || ["ITO", "NiO", "C60", "SnO2", "PEDOT:PSS", "BCP", "Ag back electrode"].includes(layer.name),
    line: { color: colors[index % colors.length], width: layer.active ? 3 : 1.6 },
  }));
}

function renderCompareChart(compare) {
  const traces = [];
  const results = Object.entries(compare).filter(([, result]) => result && typeof result === "object" && result.method);
  for (const [method, result] of results) {
    const wl = result.wavelength_nm || [];
    for (const layer of result.layers || []) {
      if (!layer.active || !layer.absorption) continue;
      traces.push({ x: wl, y: layer.absorption, type: "scatter", mode: "lines", name: `${resultLabel(result)} ${layer.name}` });
    }
  }
  const title = compare.compare_type === "rcwa_flat_vs_periodic"
    ? "RCWA planar vs RCWA periodic active-layer absorption"
    : "TMM planar vs RCWA planar active-layer absorption";
  drawPlot(traces, layout(title));
}

function renderTemperatureChart() {
  const result = state.temperatureResult;
  if (!result) {
    drawPlot([], layout("No temperature sweep yet"));
    return;
  }
  if (state.chartMode === "temp_jsc") {
    const temps = result.jsc_vs_temperature.map((item) => item.temperature_K);
    const names = new Set();
    result.jsc_vs_temperature.forEach((row) => Object.keys(row).forEach((key) => {
      if (!["temperature_K", "eg_eV"].includes(key)) names.add(key);
    }));
    const traces = [...names].map((name, index) => ({
      x: temps,
      y: result.jsc_vs_temperature.map((row) => row[name]),
      type: "scatter",
      mode: "lines+markers",
      name,
      line: { color: colors[index % colors.length], width: 2 },
    }));
    drawPlot(traces, layout("Jsc vs temperature", "Temperature (K)", "mA/cm²"));
    return;
  }
  if (state.chartMode === "temp_nk") {
    const traces = [];
    const mode = state.nkDisplayMode || "n";
    result.optical_constants.forEach((item, index) => {
      if (mode === "n" || mode === "both") {
        traces.push({ x: item.wavelength_nm, y: item.n, type: "scatter", mode: "lines", name: `${item.layer_name} n ${item.temperature_K}K`, line: { color: colors[index % colors.length], width: 3 } });
      }
      if (mode === "k" || mode === "both") {
        traces.push({ x: item.wavelength_nm, y: item.k, type: "scatter", mode: "lines", name: `${item.layer_name} k ${item.temperature_K}K`, line: { color: colors[(index + 3) % colors.length], width: 3, dash: "dot" } });
      }
    });
    drawPlot(traces, layout("Active-layer n/k vs wavelength - bandgap shift + smoothed long-wavelength tail + local KK correction", "Wavelength (nm)", mode === "k" ? "Extinction coefficient k" : "Refractive index n / k"));
    return;
  }
  const traces = [];
  result.runs.forEach((run, index) => {
    for (const layer of run.result.layers || []) {
      if (!layer.active || !layer.absorption) continue;
      traces.push({
        x: run.result.wavelength_nm,
        y: layer.absorption,
        type: "scatter",
        mode: "lines",
        name: `${layer.name} ${run.temperature_K}K`,
        line: { color: colors[index % colors.length], width: 2 },
      });
    }
  });
  drawPlot(traces, layout("Absorption vs temperature"));
}

function renderThicknessChart() {
  const result = state.thicknessResult;
  if (!result) {
    drawPlot([], layout("No thickness scan yet"));
    return;
  }
  const axes = result.scan_axes || [];
  const rows = result.results || [];
  if (!rows.length || !axes.length) {
    drawPlot([], layout("No thickness scan results"));
    return;
  }
  if (axes.length === 1) {
    const axisName = axes[0].layer_name;
    const traces = [
      { x: rows.map((row) => row[axisName]), y: rows.map((row) => row.matched), type: "scatter", mode: "lines+markers", name: "matched", line: { color: "#1f7a5c", width: 3 } },
    ];
    const activeNames = new Set();
    rows.forEach((row) => Object.keys(row.active_currents_mA_cm2 || {}).forEach((key) => {
      if (!["matched", "sum_active"].includes(key)) activeNames.add(key);
    }));
    [...activeNames].forEach((activeName, index) => {
      traces.push({ x: rows.map((row) => row[axisName]), y: rows.map((row) => row.active_currents_mA_cm2?.[activeName]), type: "scatter", mode: "lines", name: activeName, line: { color: colors[(index + 1) % colors.length], width: 2 } });
    });
    drawPlot(traces, layout("Thickness scan", `${axisName} thickness (nm)`, "mA/cm²"));
  } else {
    drawPlot([{
      x: rows.map((row) => row[axes[0].layer_name]),
      y: rows.map((row) => row[axes[1].layer_name]),
      z: rows.map((row) => row.matched),
      type: "heatmap",
      name: "matched",
    }], layout("Matched Jsc thickness map", axes[0].layer_name, axes[1].layer_name));
  }
  if (result.best) {
    $("statusText").textContent = `Best matched Jsc ${Number(result.best.matched).toFixed(3)} mA/cm²`;
  }
}

function drawPlot(traces, plotLayout) {
  if (window.Plotly) {
    Plotly.newPlot("chart", traces, plotLayout, plotConfig()).then(() => {
      const chart = $("chart");
      const hasVisiblePlot = chart.querySelector(".js-plotly-plot") && chart.querySelector(".scatterlayer, .barlayer");
      if (!hasVisiblePlot && traces.length) renderSvgFallback(traces, plotLayout);
    }).catch(() => renderSvgFallback(traces, plotLayout));
    return;
  }
  renderSvgFallback(traces, plotLayout);
}

function renderSvgFallback(traces, plotLayout) {
  const chart = $("chart");
  const width = Math.max(chart.clientWidth || 900, 640);
  const numericTraces = traces.filter((t) => Array.isArray(t.y) && t.y.length && t.visible !== false);
  if (!numericTraces.length) {
    chart.innerHTML = `<div class="plot-error">${text.noPlotly}<br>${escapeHtml(plotLayout.title?.text || text.wait)}</div>`;
    return;
  }
  const isBar = numericTraces[0].type === "bar";
  const height = isBar ? Math.max(520, 120 + numericTraces[0].y.length * 38) : Math.max(chart.clientHeight || 620, 520);
  const margin = isBar ? { left: 210, right: 120, top: 68, bottom: 86 } : { left: 78, right: 34, top: 70, bottom: 126 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const isHeatmap = numericTraces[0].type === "heatmap";
  if (isHeatmap) {
    renderHeatmapFallback(chart, numericTraces[0], plotLayout, width, height, margin, plotW, plotH);
    return;
  }
  if (isBar) {
    renderHorizontalBarFallback(chart, numericTraces[0], plotLayout, width, height, margin, plotW, plotH);
    return;
  }
  const xs = numericTraces.flatMap((t) => isBar ? t.x.map((_, i) => i) : t.x.map(Number)).filter(Number.isFinite);
  const ys = numericTraces.flatMap((t) => t.y.map(Number)).filter(Number.isFinite);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(0, Math.min(...ys));
  const yMax = Math.max(...ys) || 1;
  const xScale = (x) => margin.left + ((x - xMin) / Math.max(xMax - xMin, 1)) * plotW;
  const yScale = (y) => margin.top + plotH - ((y - yMin) / Math.max(yMax - yMin, 1e-9)) * plotH;
  const parts = [
    `<svg class="fallback-chart" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttr(plotLayout.title?.text || "chart")}" xmlns="http://www.w3.org/2000/svg">`,
    `<rect x="0" y="0" width="${width}" height="${height}" fill="#fff"/>`,
    `<text x="${margin.left}" y="34" font-size="22" font-weight="700" fill="#17201c">${escapeHtml(plotLayout.title?.text || "Chart")}</text>`,
    `<line x1="${margin.left}" y1="${margin.top + plotH}" x2="${margin.left + plotW}" y2="${margin.top + plotH}" stroke="#9aa59e"/>`,
    `<line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotH}" stroke="#9aa59e"/>`,
  ];
  makeNiceTicks(xMin, xMax, true).forEach((x) => {
    const xx = xScale(x);
    parts.push(`<line x1="${xx}" y1="${margin.top}" x2="${xx}" y2="${margin.top + plotH}" stroke="#eef1ec"/>`);
    parts.push(`<text x="${xx}" y="${margin.top + plotH + 28}" text-anchor="middle" font-size="14" fill="#4b5a52">${formatTick(x)}</text>`);
  });
  for (let i = 0; i <= 5; i++) {
    const y = yMin + (yMax - yMin) * i / 5;
    const yy = yScale(y);
    parts.push(`<line x1="${margin.left}" y1="${yy}" x2="${margin.left + plotW}" y2="${yy}" stroke="#e6eae3"/>`);
    parts.push(`<text x="${margin.left - 12}" y="${yy + 5}" text-anchor="end" font-size="14" fill="#4b5a52">${formatTick(y)}</text>`);
  }
  numericTraces.forEach((trace, index) => {
    const color = colors[index % colors.length];
    const points = smoothPoints(trace.x.map(Number), trace.y.map(Number), xScale, yScale).join(" ");
    parts.push(`<polyline fill="none" stroke="${color}" stroke-width="${Math.max(trace.line?.width || 2, 3)}" stroke-linecap="round" stroke-linejoin="round" points="${points}"/>`);
    const ly = height - 64 + Math.floor(index / 4) * 20;
    const lx = margin.left + (index % 4) * Math.max(190, plotW / 4);
    parts.push(`<line x1="${lx}" y1="${ly}" x2="${lx + 18}" y2="${ly}" stroke="${color}" stroke-width="3"/>`);
    parts.push(`<text x="${lx + 24}" y="${ly + 5}" font-size="13" fill="#17201c"><title>${escapeHtml(String(trace.name || ""))}</title>${escapeHtml(String(trace.name || `Trace ${index + 1}`).slice(0, 28))}</text>`);
  });
  parts.push(`<text x="${margin.left + plotW / 2}" y="${margin.top + plotH + 58}" text-anchor="middle" font-size="16" fill="#4b5a52">${escapeHtml(axisTitle(plotLayout.xaxis?.title))}</text>`);
  parts.push(`<text transform="translate(22,${margin.top + plotH / 2}) rotate(-90)" text-anchor="middle" font-size="16" fill="#4b5a52">${escapeHtml(axisTitle(plotLayout.yaxis?.title))}</text>`);
  parts.push(`</svg>`);
  chart.innerHTML = parts.join("");
}

function renderHorizontalBarFallback(chart, trace, plotLayout, width, height, margin, plotW, plotH) {
  const names = trace.y.map(String);
  const values = trace.x.map(Number).map((value) => Number.isFinite(value) ? value : 0);
  const xMax = Math.max(...values, 0.1) * 1.12;
  const xScale = (x) => margin.left + (Math.max(x, 0) / xMax) * plotW;
  const rowH = plotH / Math.max(values.length, 1);
  const colorsForBars = trace.marker?.color || values.map((_, index) => colors[index % colors.length]);
  const parts = [
    `<svg class="fallback-chart" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttr(plotLayout.title?.text || "chart")}" xmlns="http://www.w3.org/2000/svg">`,
    `<rect x="0" y="0" width="${width}" height="${height}" fill="#fff"/>`,
    `<text x="${margin.left}" y="34" font-size="22" font-weight="700" fill="#17201c">${escapeHtml(plotLayout.title?.text || "Layer equivalent photocurrent")}</text>`,
    `<line x1="${margin.left}" y1="${margin.top + plotH}" x2="${margin.left + plotW}" y2="${margin.top + plotH}" stroke="#9aa59e"/>`,
    `<line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotH}" stroke="#9aa59e"/>`,
  ];
  makeNiceTicks(0, xMax, false).forEach((x) => {
    const xx = xScale(x);
    parts.push(`<line x1="${xx}" y1="${margin.top}" x2="${xx}" y2="${margin.top + plotH}" stroke="#e6eae3"/>`);
    parts.push(`<text x="${xx}" y="${margin.top + plotH + 28}" text-anchor="middle" font-size="14" fill="#4b5a52">${formatTick(x)}</text>`);
  });
  values.forEach((value, index) => {
    const y = margin.top + index * rowH + rowH * 0.18;
    const barH = Math.max(8, rowH * 0.64);
    const barW = Math.max(value > 0 ? 4 : 0, xScale(value) - margin.left);
    parts.push(`<text x="${margin.left - 12}" y="${y + barH * 0.66}" text-anchor="end" font-size="14" fill="#17201c"><title>${escapeHtml(names[index])}</title>${escapeHtml(shortLabel(names[index], 24))}</text>`);
    parts.push(`<rect x="${margin.left}" y="${y}" width="${barW}" height="${barH}" rx="3" fill="${colorsForBars[index] || colors[index % colors.length]}" opacity="0.88"/>`);
    parts.push(`<text x="${Math.min(xScale(value) + 8, margin.left + plotW + 8)}" y="${y + barH * 0.66}" font-size="13" fill="#4b5a52">${formatTick(value)}</text>`);
  });
  parts.push(`<text x="${margin.left + plotW / 2}" y="${margin.top + plotH + 58}" text-anchor="middle" font-size="16" fill="#4b5a52">Equivalent current (mA/cm²)</text>`);
  parts.push(`</svg>`);
  chart.innerHTML = parts.join("");
}

function axisTitle(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (typeof value.text === "string") return value.text;
  return "";
}

function smoothPoints(xs, ys, xScale, yScale) {
  const points = [];
  for (let i = 0; i < ys.length - 1; i++) {
    const x0 = Number(xs[i]);
    const y0 = Number(ys[i]);
    const x1 = Number(xs[i + 1]);
    const y1 = Number(ys[i + 1]);
    if (!Number.isFinite(x0) || !Number.isFinite(y0) || !Number.isFinite(x1) || !Number.isFinite(y1)) continue;
    const segments = Math.max(2, Math.min(8, Math.ceil(Math.abs(x1 - x0) / 2)));
    for (let s = 0; s < segments; s++) {
      const t = s / segments;
      points.push(`${xScale(x0 + (x1 - x0) * t)},${yScale(y0 + (y1 - y0) * t)}`);
    }
  }
  const last = ys.length - 1;
  if (last >= 0 && Number.isFinite(Number(xs[last])) && Number.isFinite(Number(ys[last]))) {
    points.push(`${xScale(Number(xs[last]))},${yScale(Number(ys[last]))}`);
  }
  return points;
}

function renderHeatmapFallback(chart, trace, plotLayout, width, height, margin, plotW, plotH) {
  const xs = [...new Set(trace.x.map(Number))].sort((a, b) => a - b);
  const ys = [...new Set(trace.y.map(Number))].sort((a, b) => a - b);
  const values = trace.z.map(Number);
  const zMin = Math.min(...values);
  const zMax = Math.max(...values);
  const cellW = plotW / Math.max(xs.length, 1);
  const cellH = plotH / Math.max(ys.length, 1);
  const colorFor = (z) => {
    const t = (z - zMin) / Math.max(zMax - zMin, 1e-9);
    const r = Math.round(35 + 170 * t);
    const g = Math.round(120 + 45 * t);
    const b = Math.round(100 - 55 * t);
    return `rgb(${r},${g},${Math.max(35, b)})`;
  };
  const parts = [
    `<svg class="fallback-chart" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">`,
    `<rect x="0" y="0" width="${width}" height="${height}" fill="#fff"/>`,
    `<text x="${margin.left}" y="34" font-size="22" font-weight="700" fill="#17201c">${escapeHtml(plotLayout.title?.text || "Thickness map")}</text>`,
  ];
  trace.x.forEach((xValue, index) => {
    const xi = xs.indexOf(Number(xValue));
    const yi = ys.indexOf(Number(trace.y[index]));
    const x = margin.left + xi * cellW;
    const y = margin.top + plotH - (yi + 1) * cellH;
    parts.push(`<rect x="${x}" y="${y}" width="${cellW}" height="${cellH}" fill="${colorFor(values[index])}"/>`);
  });
  xs.forEach((xValue, index) => {
    const x = margin.left + index * cellW + cellW / 2;
    parts.push(`<text x="${x}" y="${margin.top + plotH + 26}" text-anchor="middle" font-size="14" fill="#4b5a52">${formatTick(xValue)}</text>`);
  });
  ys.forEach((yValue, index) => {
    const y = margin.top + plotH - index * cellH - cellH / 2 + 5;
    parts.push(`<text x="${margin.left - 12}" y="${y}" text-anchor="end" font-size="14" fill="#4b5a52">${formatTick(yValue)}</text>`);
  });
  parts.push(`<text x="${margin.left + plotW / 2}" y="${margin.top + plotH + 58}" text-anchor="middle" font-size="16" fill="#4b5a52">${escapeHtml(axisTitle(plotLayout.xaxis?.title))}</text>`);
  parts.push(`<text transform="translate(22,${margin.top + plotH / 2}) rotate(-90)" text-anchor="middle" font-size="16" fill="#4b5a52">${escapeHtml(axisTitle(plotLayout.yaxis?.title))}</text>`);
  parts.push(`</svg>`);
  chart.innerHTML = parts.join("");
}

function makeNiceTicks(min, max, preferHundreds = false) {
  const span = Math.max(max - min, 1);
  if (preferHundreds && span > 250) {
    const start = Math.ceil(min / 100) * 100;
    const end = Math.floor(max / 100) * 100;
    const ticks = [];
    for (let value = start; value <= end; value += 100) ticks.push(value);
    if (ticks.length >= 3) return ticks;
  }
  const rawStep = span / 6;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  const ticks = [];
  for (let value = Math.ceil(min / step) * step; value <= max + step * 0.25; value += step) {
    ticks.push(Number(value.toFixed(6)));
  }
  return ticks;
}

function shortLabel(value, maxLength = 18) {
  const textValue = String(value || "");
  return textValue.length > maxLength ? `${textValue.slice(0, maxLength - 1)}…` : textValue;
}

function formatTick(value) {
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function layout(title, xTitle = "Wavelength (nm)", yTitle = null) {
  const isCurrent = state.chartMode === "current";
  const wavelengthTicks = xTitle.includes("Wavelength") ? { tickmode: "linear", dtick: 100, tick0: 300 } : {};
  return {
    title: { text: title, font: { size: 22 } },
    font: { family: "\"Segoe UI\", \"Microsoft YaHei\", Arial, sans-serif", size: 15, color: "#17201c" },
    margin: isCurrent ? { l: 210, r: 130, t: 68, b: 92 } : { l: 78, r: 34, t: 70, b: 126 },
    xaxis: {
      title: { text: isCurrent ? "Equivalent current (mA/cm²)" : xTitle, font: { size: 16 } },
      gridcolor: "#e6eae3",
      tickfont: { size: 14 },
      automargin: true,
      ...wavelengthTicks,
    },
    yaxis: {
      title: { text: yTitle || (isCurrent ? "" : "Fraction / value"), font: { size: 16 } },
      gridcolor: "#e6eae3",
      tickfont: { size: 14 },
      automargin: true,
    },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    legend: { orientation: "h", y: -0.28, x: 0, xanchor: "left", font: { size: 13 }, traceorder: "normal" },
  };
}

function titleForMode() {
  const base = {
    absorption: "Layer absorption spectra",
    current: "Layer equivalent photocurrent",
    reflection: "Reflection / transmission",
  }[state.chartMode] || "Optical results";
  const context = modelContext(state.result);
  return context ? `${base} - ${context}` : base;
}

function plotConfig() {
  return { responsive: true, displaylogo: false };
}

function setResultChartMode(mode) {
  state.chartMode = mode;
  $("chartMode").value = mode;
  updateChartControls();
}

function updateChartControls() {
  const nkMode = $("nkDisplayMode");
  if (!nkMode) return;
  nkMode.classList.toggle("hidden", state.chartMode !== "temp_nk");
  nkMode.value = state.nkDisplayMode || "n";
}

async function exportCsv() {
  if (!state.result) return setProgress(0, text.noExport);
  const response = await fetch("/api/export/csv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.result),
  });
  downloadBlob(await response.blob(), "optical_results.csv");
}

function exportChart(format) {
  const fallback = $("chart").querySelector("svg.fallback-chart");
  if (fallback) {
    if (format === "svg") {
      downloadBlob(new Blob([fallback.outerHTML], { type: "image/svg+xml" }), "optical_chart.svg");
    } else {
      exportFallbackSvgAsPng(fallback);
    }
    return;
  }
  if (!window.Plotly) return;
  Plotly.downloadImage("chart", { format, filename: "optical_chart", width: 1800, height: 1100, scale: 2 });
}

function exportFallbackSvgAsPng(svg) {
  const xml = new XMLSerializer().serializeToString(svg);
  const img = new Image();
  const url = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml" }));
  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = 1800;
    canvas.height = 1100;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (blob) downloadBlob(blob, "optical_chart.png");
      URL.revokeObjectURL(url);
    }, "image/png");
  };
  img.src = url;
}

async function exportChartPdf() {
  const fallback = $("chart").querySelector("svg.fallback-chart");
  if (fallback) {
    const win = window.open("");
    win.document.write(`<html><head><title>optical_chart</title></head><body style="margin:0">${fallback.outerHTML}</body></html>`);
    win.document.close();
    win.focus();
    win.print();
    return;
  }
  if (!window.Plotly) return;
  const url = await Plotly.toImage("chart", { format: "png", width: 1400, height: 900, scale: 2 });
  const win = window.open("");
  win.document.write(`<html><head><title>optical_chart</title></head><body style="margin:0"><img src="${url}" style="width:100%"></body></html>`);
  win.document.close();
  win.focus();
  win.print();
}

function saveProject(showMessage = true) {
  const project = {
    appVersion: APP_VERSION,
    payload: buildPayload(),
    result: state.result,
    compare: state.compare,
    temperatureResult: state.temperatureResult,
    thicknessResult: state.thicknessResult,
    bandgapModels: state.bandgapModels,
    method: state.method,
    compareType: state.compareType,
    chartMode: state.chartMode,
    nkDisplayMode: state.nkDisplayMode,
    periodic: state.periodic,
  };
  localStorage.setItem("opticsProject", JSON.stringify(project));
  if (showMessage) setProgress(100, text.saved);
}

function restoreProject() {
  const raw = localStorage.getItem("opticsProject");
  if (!raw) return;
  try {
    const project = JSON.parse(raw);
    if (project.appVersion !== APP_VERSION) {
      localStorage.removeItem("opticsProject");
      return;
    }
    applyProject(project);
    setProgress(100, text.restored);
  } catch {
    localStorage.removeItem("opticsProject");
  }
}

function exportProject() {
  saveProject(false);
  downloadBlob(new Blob([localStorage.getItem("opticsProject")], { type: "application/json" }), "optics_project.json");
}

async function importProject(event) {
  const file = event.target.files[0];
  if (!file) return;
  applyProject(JSON.parse(await file.text()));
  renderLayers();
  renderMetrics(state.result);
  renderChart();
  setProgress(100, text.imported);
}

function applyProject(project) {
  const payload = project.payload || project;
  state.layers = payload.layers || state.layers;
  state.result = project.result || null;
  state.compare = project.compare || null;
  state.temperatureResult = project.temperatureResult || null;
  state.thicknessResult = project.thicknessResult || null;
  state.bandgapModels = project.bandgapModels || [];
  state.method = project.method || "tmm";
  state.compareType = project.compareType || payload.compare_type || "tmm_flat_vs_rcwa_flat";
  state.chartMode = project.chartMode || "absorption";
  state.nkDisplayMode = project.nkDisplayMode || "n";
  state.periodic = project.periodic ?? payload.rcwa?.periodic ?? payload.rcwa?.shape !== "Planar";
  $("wlStart").value = payload.wavelength?.start_nm ?? 300;
  $("wlStop").value = payload.wavelength?.stop_nm ?? 1060;
  $("wlStep").value = payload.wavelength?.step_nm ?? 2;
  $("rcwaShape").value = payload.rcwa?.shape === "Planar" ? "Paraboloid" : payload.rcwa?.shape ?? "Paraboloid";
  $("rcwaPitch").value = payload.rcwa?.pitch ?? 500;
  $("rcwaHeight").value = payload.rcwa?.height ?? 500;
  $("rcwaDuty").value = payload.rcwa?.duty_cycle ?? 0.5;
  $("rcwaNG").value = payload.rcwa?.nG ?? 17;
  $("rcwaSlices").value = payload.rcwa?.slices ?? 12;
  $("rcwaWbg").value = payload.rcwa?.t_wbg ?? 410;
  $("rcwaNbg").value = payload.rcwa?.t_nbg ?? 800;
  $("tempList").value = (payload.temperature?.temperatures_K || [280, 300, 320]).join(",");
  $("tempRef").value = payload.temperature?.reference_K ?? 300;
  if (payload.temperature?.bandgap_models) state.bandgapModels = payload.temperature.bandgap_models;
  $("chartMode").value = state.chartMode;
  $("compareType").value = state.compareType;
  updateChartControls();
  setMethod(state.method);
  setPeriodic(state.periodic);
  syncBandgapModels();
  renderBandgapEditor();
  renderThicknessEditor();
}

async function validateMaterial(event) {
  const file = event.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/materials/validate", { method: "POST", body: form });
  $("materialPreview").textContent = JSON.stringify(await response.json(), null, 2);
}

async function api(path, body) {
  const response = await fetch(path, body === undefined ? undefined : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await response.json();
  if (!response.ok) throw new Error(json.error || response.statusText);
  return json;
}

function setProgress(progress, message) {
  $("progressBar").style.width = `${Math.max(0, Math.min(100, progress))}%`;
  $("statusText").textContent = message;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function escapeAttr(value) {
  return escapeHtml(value ?? "");
}

init().catch((error) => setProgress(0, error.message));
