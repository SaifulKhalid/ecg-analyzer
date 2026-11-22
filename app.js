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

let selectedImage = '';
let selection = 0;

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function clearImage() {
  selection += 1;
  selectedImage = '';
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

function renderReport(report) {
  result.replaceChildren();
  const scroll = document.createElement('div');
  scroll.className = 'table-scroll';
  scroll.tabIndex = 0;
  scroll.setAttribute('role', 'region');
  scroll.setAttribute('aria-label', 'Key numerical findings');
  const table = document.createElement('table');
  table.className = 'findings-table';
  const caption = table.createCaption();
  caption.textContent = 'Key numerical findings';
  const heading = table.createTHead().insertRow();
  for (const label of ['Measurement', 'Value', 'Unit', 'Finding']) {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = label;
    heading.append(cell);
  }
  const body = table.createTBody();
  for (const measurement of report.measurements) {
    const row = body.insertRow();
    const label = document.createElement('th');
    label.scope = 'row';
    label.textContent = measurement.label;
    row.append(label);
    for (const value of [measurement.value ?? 'Not measurable', measurement.unit, measurement.note]) {
      row.insertCell().textContent = value;
    }
  }
  scroll.append(table);
  const explanation = document.createElement('div');
  explanation.className = 'report-explanation';
  for (const paragraph of report.explanation) {
    const element = document.createElement('p');
    element.textContent = paragraph;
    explanation.append(element);
  }
  result.append(scroll, explanation);
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

analyzeButton.addEventListener('click', async () => {
  if (!selectedImage || analyzeButton.disabled) return;

  analyzeButton.disabled = true;
  analyzeButton.textContent = 'Analyzing…';
  imageInput.disabled = true;
  removeButton.disabled = true;
  errorMessage.hidden = true;
  resultSection.hidden = true;
  resultSection.setAttribute('aria-busy', 'true');
  const started = performance.now();
  const updateStatus = () => {
    status.textContent = `Analyzing the ECG… ${Math.floor((performance.now() - started) / 1000)} seconds elapsed.`;
  };
  updateStatus();
  const progressTimer = setInterval(updateStatus, 1000);
  status.hidden = false;

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: selectedImage }),
      signal: AbortSignal.timeout(130_000),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.error || 'The analysis failed. Please try again.');
    if (!Array.isArray(data?.report?.measurements) || !data.report.measurements.length
      || !Array.isArray(data.report.explanation) || !data.report.explanation.length) {
      throw new Error('No analysis was returned. Please try again.');
    }

    renderReport(data.report);
    const duration = (performance.now() - started) / 1000;
    analysisTime.textContent = `Completed in ${duration.toFixed(1)} seconds.`;
    resultSection.hidden = false;
    document.querySelector('#result-heading').focus();
  } catch (error) {
    showError(error.name === 'TimeoutError'
      ? 'The analysis took too long. Please try again.'
      : error instanceof TypeError
        ? 'Could not reach the server. Check your connection and try again.'
        : error.message);
  } finally {
    clearInterval(progressTimer);
    analyzeButton.disabled = false;
    analyzeButton.textContent = 'Analyze ECG';
    imageInput.disabled = false;
    removeButton.disabled = false;
    resultSection.setAttribute('aria-busy', 'false');
    status.hidden = true;
  }
});
