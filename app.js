const imageInput = document.querySelector('#image-input');
const previewSection = document.querySelector('#preview-section');
const preview = document.querySelector('#preview');
const fileName = document.querySelector('#file-name');
const removeButton = document.querySelector('#remove-button');
const analyzeButton = document.querySelector('#analyze-button');
const status = document.querySelector('#status');
const errorMessage = document.querySelector('#error');
const resultSection = document.querySelector('#result-section');
const result = document.querySelector('#result');
const analysisTime = document.querySelector('#analysis-time');
const demoSelect = document.querySelector('#demo-select');
const demoButton = document.querySelector('#demo-button');
const demoReload = document.querySelector('#demo-reload');
const explainEnabled = document.querySelector('#explain-enabled');
const providerDefault = document.querySelector('#provider-default');
const notchHz = document.querySelector('#notch-hz');

let selectedImage = '';
let selectedFile = null;
let selection = 0;
let busy = false;
let catalogReady = false;

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function clearImage() {
  selection += 1;
  selectedImage = '';
  selectedFile = null;
  preview.removeAttribute('src');
  previewSection.hidden = true;
  resultSection.hidden = true;
  result.textContent = '';
  analysisTime.textContent = '';
  errorMessage.hidden = true;
  status.hidden = true;
  fileName.textContent = '';
}

function readImage(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('The image could not be opened. Choose another file.'));
    reader.readAsDataURL(file);
  });
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatNumber(value, digits = 1) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'Unavailable';
}

function renderReport(data) {
  result.replaceChildren();
  const measurements = data.measurements;
  const sufficient = data.status === 'ok';
  const source = data.source?.label || data.source?.source || 'Single-lead ECG';
  result.append(element('p', 'result-source', source));
  const quality = element('div', sufficient ? 'quality-panel' : 'quality-panel quality-poor');
  quality.append(element('strong', 'quality-status', sufficient ? 'Signal quality check passed' : 'Insufficient signal quality'));
  quality.append(element('p', 'help', `${measurements.beat_count} detected beats · ${formatNumber(measurements.duration_s)} s · estimated SNR ${formatNumber(data.quality.snr_db)} dB (heuristic)`));
  if (!sufficient) for (const reason of data.quality.reasons || []) quality.append(element('p', 'quality-reason', reason));
  result.append(quality);

  const cards = element('div', 'metric-cards');
  for (const metric of [
    ['Heart rate', measurements.hr_mean_bpm, 'bpm', `${formatNumber(measurements.hr_min_bpm)}–${formatNumber(measurements.hr_max_bpm)} bpm per RR interval`],
    ['SDNN', measurements.sdnn_ms, 'ms', 'Standard deviation of detected RR'],
    ['RMSSD', measurements.rmssd_ms, 'ms', 'Successive RR differences'],
  ]) {
    const card = element('div', 'metric-card');
    card.append(element('h3', 'metric-label', metric[0]));
    const value = element('p', 'metric-value', sufficient ? formatNumber(metric[1]) : '—');
    value.append(element('span', 'metric-unit', sufficient ? ` ${metric[2]}` : ''));
    card.append(value, element('p', 'help', sufficient ? metric[3] : 'A clearer / longer strip is required'));
    cards.append(card);
  }
  result.append(cards);

  const details = element('details', 'measurement-details');
  details.append(element('summary', '', 'All measured rate and RR values'));
  const scroll = element('div', 'table-scroll');
  scroll.tabIndex = 0;
  scroll.setAttribute('role', 'region');
  scroll.setAttribute('aria-label', 'Measured numerical findings');
  const table = element('table', 'findings-table');
  table.createCaption().textContent = 'Signal-processing measurements';
  const heading = table.createTHead().insertRow();
  for (const label of ['Measurement', 'Value', 'Unit', 'Meaning']) {
    const cell = element('th', '', label);
    cell.scope = 'col';
    heading.append(cell);
  }
  const rows = [
    ['Mean heart rate', measurements.hr_mean_bpm, 'bpm', '60 / mean RR'],
    ['Minimum heart rate', measurements.hr_min_bpm, 'bpm', 'From the longest RR interval'],
    ['Maximum heart rate', measurements.hr_max_bpm, 'bpm', 'From the shortest RR interval'],
    ['Mean RR', measurements.mean_rr_ms, 'ms', 'Mean time between R events'],
    ['SDNN', measurements.sdnn_ms, 'ms', 'Sample standard deviation of detected RR'],
    ['RMSSD', measurements.rmssd_ms, 'ms', 'Root mean square of successive RR differences'],
    ['pNN50', measurements.pnn50_percent, '%', 'Successive RR differences greater than 50 ms'],
    ['RR coefficient of variation', measurements.rr_cv, '', 'RR standard deviation / mean RR'],
  ];
  const body = table.createTBody();
  for (const measurement of rows) {
    const row = body.insertRow();
    const label = element('th', '', measurement[0]);
    label.scope = 'row';
    row.append(label);
    for (const value of [formatNumber(measurement[1], measurement[0].includes('coefficient') ? 4 : 1), measurement[2], measurement[3]]) row.insertCell().textContent = value;
  }
  scroll.append(table);
  details.append(scroll, element('p', 'help', measurements.variability_note));
  result.append(details);

  const findings = element('div', 'screening-findings');
  findings.append(element('h3', 'panel-heading', 'Possible findings'));
  if (!data.findings?.length) findings.append(element('p', 'help', 'Screening flags are skipped when signal quality is insufficient.'));
  for (const finding of data.findings || []) {
    const card = element('div', 'finding-card');
    const header = element('div', 'finding-heading');
    header.append(element('strong', '', finding.label));
    header.append(element('span', 'confidence-badge', `Heuristic ${Math.round(finding.confidence * 100)}%`));
    const evidence = element('ul', 'finding-evidence');
    for (const item of finding.evidence || []) evidence.append(element('li', '', item));
    card.append(header, evidence);
    findings.append(card);
  }
  findings.append(element('p', 'help', 'Confidence badges are engineering heuristics, not disease probabilities.'));
  result.append(findings);

  const plots = element('div', 'plot-list');
  const plotDefinitions = [
    ['raw_filtered', 'Raw and filtered ECG', 'Slow baseline drift and high-frequency artifact are attenuated. Waveform preview: first 10 seconds.'],
    ['spectrum', 'Power spectrum before and after filtering', 'Full-strip spectrum. The dashed line marks the selected mains notch.'],
    ['r_peaks', 'Filtered ECG with detected R events', 'Red markers show the beat events used for all RR measurements.'],
    ['rr_tachogram', 'RR tachogram', 'All RR intervals across the full strip. Variability includes possible ectopy and detection errors.'],
  ];
  for (const [key, title, caption] of plotDefinitions) {
    if (!data.plots?.[key]) continue;
    const figure = element('figure', 'evidence-plot');
    const image = element('img');
    image.src = `data:image/png;base64,${data.plots[key]}`;
    image.alt = title;
    image.loading = 'lazy';
    figure.append(element('h3', 'panel-heading', title), image, element('figcaption', 'help', caption));
    plots.append(figure);
  }
  result.append(plots);
  if (data.plots?.digitization) {
    const debug = element('details', 'digitization-debug');
    debug.append(element('summary', '', 'Image digitization overlay'));
    const overlay = element('img');
    overlay.src = `data:image/png;base64,${data.plots.digitization}`;
    overlay.alt = 'Recovered ECG trace in green with the selected crop boundary';
    debug.append(overlay);
    const calibration = data.source?.calibration;
    if (calibration) debug.append(element('p', 'help', `${formatNumber(calibration.pixels_per_mm, 2)} pixels/mm · ${calibration.paper_speed} mm/s · ${calibration.gain} mm/mV · ${calibration.method}`));
    result.append(debug);
  }

  const explanation = element('div', 'report-explanation');
  explanation.append(element('h3', 'panel-heading', 'AI explanation of measured JSON'));
  if (data.explanation_settings?.used_provider_default) {
    explanation.append(element('p', 'provider-note', 'Compatibility mode used the provider default temperature after 0.2 was rejected. AI received the measured JSON only.'));
  }
  if (data.explanation && typeof data.explanation === 'object') {
    for (const section of ['Summary', 'What the numbers mean', 'Possible findings', 'Limitations', 'When to see a doctor']) {
      if (!data.explanation[section]) continue;
      explanation.append(element('h4', '', section), element('p', '', data.explanation[section]));
    }
  } else {
    explanation.append(element('p', 'help', 'No AI explanation is available. The measured results above remain available.'));
    if (data.explanation_error) explanation.append(element('p', 'provider-note', data.explanation_error));
  }
  result.append(explanation);
  const limitations = element('details', 'limitations-panel');
  limitations.append(element('summary', '', 'Limitations and warnings'));
  const warnings = element('ul');
  for (const warning of data.warnings || []) warnings.append(element('li', '', warning));
  limitations.append(warnings);
  result.append(limitations);
  const json = element('details', 'json-panel');
  json.append(element('summary', '', 'Inspect measured JSON'));
  json.append(element('pre', '', JSON.stringify({ quality: data.quality, measurements: data.measurements,
    findings: data.findings, explanation_grounding: data.explanation_grounding,
    explanation_settings: data.explanation_settings }, null, 2)));
  result.append(json, element('p', 'disclaimer', 'Educational screening tool, not a medical device.'));
}

imageInput.addEventListener('change', async () => {
  clearImage();
  const currentSelection = selection;
  const file = imageInput.files[0];
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    imageInput.value = '';
    return showError('Choose a PNG, JPG, or WebP image.');
  }
  if (file.size === 0 || file.size > 10 * 1024 * 1024) {
    imageInput.value = '';
    return showError('Choose a non-empty image under 10 MB.');
  }
  status.textContent = 'Opening image…';
  status.hidden = false;
  try {
    const image = await readImage(file);
    const check = new Image();
    check.src = image;
    await check.decode();
    if (currentSelection !== selection) return;
    selectedImage = image;
    selectedFile = file;
    preview.src = image;
    fileName.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    previewSection.hidden = false;
    status.hidden = true;
  } catch {
    if (currentSelection !== selection) return;
    imageInput.value = '';
    status.hidden = true;
    showError('The image could not be opened. Choose a valid image file.');
  }
});

removeButton.addEventListener('click', () => {
  clearImage();
  imageInput.value = '';
  imageInput.focus();
});

function setBusy(value) {
  busy = value;
  for (const control of [imageInput, removeButton, analyzeButton, demoSelect, demoButton, demoReload, ...document.querySelectorAll('[data-lock]')]) control.disabled = value;
  if (!value) demoSelect.disabled = demoButton.disabled = !catalogReady;
}

async function runAnalysis(path, body, button) {
  if (busy) return;
  setBusy(true);
  const originalLabel = button.textContent;
  button.textContent = 'Measuring…';
  errorMessage.hidden = true;
  resultSection.hidden = true;
  resultSection.setAttribute('aria-busy', 'true');
  const started = performance.now();
  const updateStatus = () => {
    status.textContent = `${explainEnabled.checked ? 'Measuring and requesting an explanation' : 'Measuring the ECG'}… ${Math.floor((performance.now() - started) / 1000)} seconds elapsed.`;
  };
  updateStatus();
  const timer = setInterval(updateStatus, 1000);
  status.hidden = false;
  try {
    const form = body instanceof FormData;
    const response = await fetch(path, { method: 'POST',
      ...(form ? {} : { headers: { 'Content-Type': 'application/json' } }),
      body: form ? body : JSON.stringify(body), signal: AbortSignal.timeout(130_000) });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.error || (typeof data?.detail === 'string' ? data.detail : 'The measurement request failed. Check the input and try again.'));
    if (!data?.measurements || !data.quality || !Array.isArray(data.findings)) throw new Error('No measured report was returned.');
    renderReport(data);
    analysisTime.textContent = `Completed in ${((performance.now() - started) / 1000).toFixed(1)} seconds. Metrics use the full strip.`;
    resultSection.hidden = false;
    document.querySelector('#result-heading').focus();
  } catch (error) {
    showError(error.name === 'TimeoutError' ? 'The analysis took too long. Please try again.'
      : error instanceof TypeError ? 'Could not reach the server. Check your connection and try again.' : error.message);
  } finally {
    clearInterval(timer);
    setBusy(false);
    button.textContent = originalLabel;
    resultSection.setAttribute('aria-busy', 'false');
    status.hidden = true;
  }
}

analyzeButton.addEventListener('click', () => {
  if (!selectedImage || !selectedFile || busy) return;
  const body = new FormData();
  body.set('image', selectedFile);
  for (const [id, name] of [['pixels-per-mm', 'pixels_per_mm'], ['paper-speed', 'paper_speed'], ['gain', 'gain']]) {
    const input = document.getElementById(id);
    if (!input.checkValidity()) return showError(`Enter a valid ${name.replaceAll('_', ' ')}.`);
    if (input.value.trim()) body.set(name, input.value);
  }
  const crop = document.querySelector('#crop-box').value.trim();
  if (crop) {
    const bounds = crop.split(',').map(value => Number(value.trim()));
    if (bounds.length !== 4 || !bounds.every(Number.isInteger) || bounds.some(value => value < 0)
      || bounds[2] <= bounds[0] || bounds[3] <= bounds[1]) return showError('Crop must be four integers: left, top, right, bottom.');
    body.set('crop_box', JSON.stringify(bounds));
  }
  body.set('explain', String(explainEnabled.checked));
  body.set('allow_provider_default_temperature', String(providerDefault.checked));
  body.set('notch_hz', notchHz.value);
  runAnalysis('/analyze', body, analyzeButton);
});

demoButton.addEventListener('click', () => {
  if (!demoSelect.value || busy) return;
  runAnalysis('/analyze-signal', { sample_id: demoSelect.value, explain: explainEnabled.checked,
    allow_provider_default_temperature: providerDefault.checked, notch_hz: Number(notchHz.value) }, demoButton);
});

async function loadDemos() {
  if (busy) return;
  catalogReady = false;
  demoSelect.disabled = demoButton.disabled = demoReload.disabled = true;
  try {
    const response = await fetch('/samples', { signal: AbortSignal.timeout(10_000) });
    const samples = await response.json();
    if (!response.ok || !Array.isArray(samples) || !samples.length) throw new Error('Could not load demo records. Start the FastAPI service and refresh the demo list.');
    demoSelect.replaceChildren();
    for (const sample of samples) {
      const option = element('option', '', sample.label);
      option.value = sample.sample_id;
      demoSelect.append(option);
    }
    catalogReady = true;
    errorMessage.hidden = true;
  } catch (error) {
    demoSelect.replaceChildren(element('option', '', 'Demos unavailable'));
    showError(error.message);
  } finally {
    demoSelect.disabled = demoButton.disabled = !catalogReady;
    demoReload.disabled = false;
  }
}

demoReload.addEventListener('click', loadDemos);
loadDemos();
