const imageInput = document.querySelector('#image-input');
const demoSelect = document.querySelector('#demo-select');
const analyzeButton = document.querySelector('#analyze-button');
const resultSection = document.querySelector('#result-section');
const result = document.querySelector('#result');
let selectedFile = null, preview = '', currentReport = null;
let resized = false, uploadScale = 1, busy = false, generation = 0;

function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}
function number(value, digits = 1) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'n/a';
}
function imageSource(encoded) {
  return /^(data|blob):/.test(encoded) ? encoded : `data:image/${encoded.startsWith('/9j/') ? 'jpeg' : 'png'};base64,${encoded}`;
}
function cleanReason(reason) {
  return String(reason).replace(/\bscreening\b/gi, 'measurement').replace(/\bpossible\b/gi, '').replace(/\s+/g, ' ').trim().replace(/[.]$/, '');
}
function reportNotes(data) {
  const notes = [...(data.notes || [])];
  for (const warning of data.warnings || []) {
    if (/^(Automatic calibration|Image conversion assumes|Manual pixels\/mm|Only one grid|Grid spacing|Image has only|Interpolated|Filter edge)/.test(warning)) notes.push(warning);
  }
  if (data.status === 'insufficient_quality') notes.push(...(data.quality?.reasons || []).map(cleanReason));
  if (resized && selectedFile) notes.push('Image resized before upload.');
  return [...new Set(notes.map(line => String(line).trim()).filter(Boolean))];
}

function renderReport(data) {
  currentReport = data;
  result.replaceChildren();
  document.querySelector('#report-actions').hidden = data.status === 'no_ecg_detected';
  if (data.status === 'no_ecg_detected') {
    result.append(element('p', 'No ECG trace detected in the image.')); return;
  }
  if (data.status === 'insufficient_quality') {
    const reasons = [...new Set((data.quality?.reasons || []).map(cleanReason))];
    const notice = element('p', `Signal quality below threshold: ${reasons.join('; ')}. Values may be unreliable.`);
    notice.className = 'quality-notice'; result.append(notice);
  }
  let count = 0;
  function figure(title, src, region) {
    if (!src) return;
    const container = element('figure'), frame = element('div'), img = element('img');
    frame.className = 'image-frame'; img.src = imageSource(src); img.alt = title; frame.append(img);
    if (region?.box) {
      const outline = element('div'); outline.className = 'region-outline'; outline.setAttribute('aria-hidden', 'true');
      img.addEventListener('load', () => {
        const [left, top, right, bottom] = region.box;
        const [width, height] = region.image_size || [img.naturalWidth, img.naturalHeight];
        outline.style.left = `${100 * left / width}%`; outline.style.top = `${100 * top / height}%`;
        outline.style.width = `${100 * (right-left) / width}%`; outline.style.height = `${100 * (bottom-top) / height}%`;
      }, { once: true });
      frame.append(outline);
    }
    container.append(frame, element('figcaption', `Figure ${++count}. ${title}.`)); result.append(container);
  }
  const uploaded = data.plots?.prepared_image || (selectedFile ? preview : null);
  if (uploaded) figure(data.region_selection ? 'Uploaded image with analyzed region outlined' : 'Uploaded image', uploaded, data.region_selection);
  for (const [key, title] of [
    ['raw_filtered', 'Raw and filtered ECG'], ['spectrum', 'Power spectrum before and after filtering'],
    ['r_peaks', 'Filtered ECG with detected R peaks'], ['rr_tachogram', 'RR tachogram'],
  ]) if (data.plots?.[key]) figure(title, data.plots[key]);
  if (uploaded && data.plots?.digitization) figure('Digitized trace overlaid on the uploaded image', data.plots.digitization);

  const m = data.measurements || {}, table = element('table');
  table.createCaption().textContent = 'Table 1. Measured values.';
  const header = table.createTHead().insertRow();
  for (const label of ['Parameter', 'Value', 'Unit']) { const cell = element('th', label); cell.scope = 'col'; header.append(cell); }
  const body = table.createTBody();
  for (const [parameter, value, unit] of [
    ['Record duration', number(m.duration_s), 's'], ['Sampling rate after resampling', number(m.fs_hz, 0), 'Hz'],
    ['R peaks detected', number(m.beat_count, 0), ''], ['Mean heart rate', number(m.hr_mean_bpm), 'bpm'],
    ['Minimum / maximum heart rate', m.hr_min_bpm == null && m.hr_max_bpm == null ? 'n/a' : `${number(m.hr_min_bpm)} / ${number(m.hr_max_bpm)}`, 'bpm'],
    ['Mean RR interval', number(m.mean_rr_ms, 0), 'ms'], ['SDNN', number(m.sdnn_ms, 0), 'ms'],
    ['RMSSD', number(m.rmssd_ms, 0), 'ms'], ['pNN50', number(m.pnn50_percent), '%'],
    ['RR coefficient of variation', number(typeof m.rr_cv === 'number' ? m.rr_cv * 100 : null), '%'],
    ['Signal-to-noise ratio', number(data.quality?.snr_db), 'dB'],
  ]) {
    const row = body.insertRow(), label = element('th', parameter); label.scope = 'row'; row.append(label);
    row.insertCell().textContent = value; row.insertCell().textContent = unit;
  }
  result.append(table);
  const notes = reportNotes(data);
  if (notes.length) {
    result.append(element('h2', 'Notes'));
    for (const line of notes) { const note = element('p', line); note.className = 'note'; result.append(note); }
  }
}

function setBusy(value) {
  busy = value;
  for (const control of document.querySelectorAll('#input-form button, #input-form input, #input-form select')) control.disabled = value;
  analyzeButton.disabled = value || (!selectedFile && !demoSelect.value);
  resultSection.setAttribute('aria-busy', String(value));
}
async function prepareUpload(file) {
  if (!file.size || file.size > 25_000_000) throw new Error('input');
  const readImage = blob => new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('input')); reader.readAsDataURL(blob);
  });
  const url = await readImage(file), img = new Image();
  try {
    img.src = url; await img.decode();
    if (file.size <= 3_500_000) return { file, preview: url, resized: false, scale: 1 };
    let scale = Math.min(1, 3000 / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement('canvas'); let blob;
    for (let attempt = 0; attempt < 5; attempt += 1) {
      canvas.width = Math.max(1, Math.round(img.naturalWidth * scale)); canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
      const context = canvas.getContext('2d'); context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(img, 0, 0, canvas.width, canvas.height);
      blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
      if (blob && blob.size <= 3_500_000) break;
      scale *= blob ? Math.min(0.8, Math.sqrt(3_300_000 / blob.size)) : 0.7;
    }
    if (!blob || blob.size > 3_500_000) throw new Error('input');
    URL.revokeObjectURL(url);
    return { file: new File([blob], file.name, { type: 'image/jpeg' }), preview: await readImage(blob), resized: true, scale };
  } catch (error) { URL.revokeObjectURL(url); throw error; }
}
document.querySelector('#choose-file').addEventListener('click', () => imageInput.click());
imageInput.addEventListener('change', async () => {
  const ticket = ++generation; selectedFile = null;
  if (preview) URL.revokeObjectURL(preview);
  preview = ''; resized = false; uploadScale = 1; resultSection.hidden = true;
  const file = imageInput.files[0]; if (!file) { setBusy(false); return; }
  setBusy(true);
  try {
    const prepared = await prepareUpload(file);
    if (ticket !== generation) { URL.revokeObjectURL(prepared.preview); return; }
    selectedFile = prepared.file; preview = prepared.preview; resized = prepared.resized; uploadScale = prepared.scale; demoSelect.value = '';
  } catch { imageInput.value = ''; }
  finally { if (ticket === generation) setBusy(false); }
});
demoSelect.addEventListener('change', () => {
  generation += 1; selectedFile = null; resized = false;
  if (preview) URL.revokeObjectURL(preview);
  preview = ''; imageInput.value = ''; resultSection.hidden = true; setBusy(false);
});
document.querySelector('#input-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy || (!selectedFile && !demoSelect.value)) return;
  const notch_hz = Number(document.querySelector('#notch-hz').value); let body, path;
  if (selectedFile) {
    body = new FormData(); path = '/analyze'; body.set('image', selectedFile, selectedFile.name);
    for (const [id, name] of [['pixels-per-mm', 'pixels_per_mm'], ['paper-speed', 'paper_speed'], ['gain', 'gain']]) {
      const value = document.getElementById(id).value.trim();
      if (value) body.set(name, name === 'pixels_per_mm' ? String(Number(value) * uploadScale) : value);
    }
    const crop = document.querySelector('#crop-box').value.trim();
    if (crop) {
      const bounds = crop.split(',').map(value => Number(value.trim()));
      if (bounds.length !== 4 || !bounds.every(Number.isInteger) || bounds.some(value => value < 0) || bounds[2] <= bounds[0] || bounds[3] <= bounds[1]) return;
      body.set('crop_box', JSON.stringify(bounds.map(value => Math.round(value * uploadScale))));
    }
    body.set('explain', 'false'); body.set('notch_hz', String(notch_hz));
  } else { path = '/analyze-signal'; body = { sample_id: demoSelect.value, explain: false, notch_hz }; }
  setBusy(true); resultSection.hidden = true;
  try {
    const form = body instanceof FormData;
    const response = await fetch(path, { method: 'POST', ...(form ? {} : { headers: { 'Content-Type': 'application/json' } }),
      body: form ? body : JSON.stringify(body), signal: AbortSignal.timeout(130_000) });
    const data = await response.json(); if (!response.ok) return;
    renderReport(data); resultSection.hidden = false;
  } catch { /* No transport-error text is included in the copy deck. */ }
  finally { setBusy(false); }
});
document.querySelector('#download-json').addEventListener('click', () => {
  if (!currentReport) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify({ ...currentReport, notes: reportNotes(currentReport) }, null, 2)], { type: 'application/json' }));
  const link = element('a'); link.href = url; link.download = 'ecg-measurements.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
document.querySelector('#print-button').addEventListener('click', () => window.print());
async function loadSamples() {
  try {
    const response = await fetch('/samples', { signal: AbortSignal.timeout(10_000) }); const samples = await response.json();
    if (!response.ok || !Array.isArray(samples)) return;
    for (const sample of samples) { const option = element('option', sample.sample_id); option.value = sample.sample_id; demoSelect.append(option); }
  } catch { /* A file remains an input when the catalog is unavailable. */ }
}
loadSamples();
