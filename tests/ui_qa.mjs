// Local Chromium CDP QA: no additional runtime or testing dependencies.
import assert from 'node:assert/strict';
import { writeFile, mkdir, stat } from 'node:fs/promises';
import path from 'node:path';

const port = Number(process.env.ECG_QA_CDP_PORT || 9223);
const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const tab = tabs.find(item => item.type === 'page');
const socket = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
let id = 0;
const pending = new Map(), errors = [], requests = [];
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const handlers = pending.get(message.id); pending.delete(message.id);
    if (message.error) handlers.reject(new Error(message.error.message)); else handlers.resolve(message.result);
  } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
  else if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error') errors.push(message.params.entry.text);
  else if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') errors.push('Browser console error');
  else if (message.method === 'Network.requestWillBeSent' && /\/analyze(?:-signal)?$/.test(message.params.request.url)) requests.push(message.params.request);
});
function send(method, params = {}) {
  return new Promise((resolve, reject) => { const next = ++id; pending.set(next, { resolve, reject }); socket.send(JSON.stringify({ id: next, method, params })); });
}
async function evaluate(expression) {
  const answer = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (answer.exceptionDetails) throw new Error(answer.exceptionDetails.text);
  return answer.result.value;
}
async function until(expression, timeout = 60_000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await evaluate(expression)) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out: ${expression}`);
}
await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable'); await send('DOM.enable');
await send('Log.enable');
await send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: path.resolve('test-results') });
await mkdir('test-results', { recursive: true });
const rows = [];
const imagePath = path.resolve(process.argv[2] || 'test-results/report-strip.png');
const label = process.argv[3] || 'part-b';
for (const width of [1280, 390]) {
  await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false });
  for (const input of ['sample', 'image']) {
    await send('Page.navigate', { url: 'http://127.0.0.1:3000/' });
    await until(`document.querySelector('#demo-select')?.options.length > 1`);
    assert.equal(await evaluate(`document.querySelector('#calibration').open`), false);
    if (input === 'sample') await evaluate(`document.querySelector('#demo-select').value='mitdb-100';document.querySelector('#demo-select').dispatchEvent(new Event('change'));`);
    else {
      const document = await send('DOM.getDocument');
      const field = await send('DOM.querySelector', { nodeId: document.root.nodeId, selector: '#image-input' });
      await send('DOM.setFileInputFiles', { nodeId: field.nodeId, files: [imagePath] });
      await until(`!document.querySelector('#analyze-button').disabled`);
    }
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('#analyze-button')).backgroundColor`), 'rgb(31, 58, 95)');
    await evaluate(`document.querySelector('#analyze-button').click()`);
    await until(`!document.querySelector('#result-section').hidden && !document.querySelector('#analyze-button').disabled`);
    await until(`[...document.querySelectorAll('#result img')].every(img=>img.complete && img.naturalWidth>0)`);
    const info = await evaluate(`({text:document.body.innerText, overflow:document.documentElement.scrollWidth>innerWidth, figures:[...document.querySelectorAll('figcaption')].map(x=>x.innerText), rows:[...document.querySelectorAll('tbody tr')].map(x=>x.innerText), notes:[...document.querySelectorAll('.note')].map(x=>x.innerText), outline:!!document.querySelector('.region-outline')})`);
    assert.equal(info.overflow, false);
    assert.doesNotMatch(info.text, /\b(AI|screening|findings|possible|confidence|insight|powerful|seamless)\b/i);
    assert.equal(info.figures.length, input === 'sample' ? 4 : 6);
    info.figures.forEach((caption, index) => assert.match(caption, new RegExp(`^Figure ${index+1}\\. .+\\.$`)));
    assert.equal(info.rows.length, 11);
    assert.doesNotMatch(info.text, /\bNotes\b|Educational tool, not a medical device|Interpretation is left to a qualified clinician/);
    assert.doesNotMatch(info.text, /Completed in|Limitations|Refresh demo|Inspect measured|Measuring/);
    await writeFile(`test-results/${label}-${input}-${width}-dom.txt`, info.text);
    assert.equal(await evaluate(`document.querySelector('#crop-box').value`), '');
    assert.equal(info.notes.length, 0);
    if (label !== 'part-b' && input === 'image') assert.equal(info.outline, true);
    if (info.outline) {
      const border = await evaluate(`getComputedStyle(document.querySelector('.region-outline')).borderTopWidth`);
      assert.equal(border, '2px');
      assert.equal(await evaluate(`document.querySelector('.region-outline').getBoundingClientRect().width>0`), true);
    }
    await send('Emulation.setEmulatedMedia', { media: 'print' });
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('#input-section')).display`), 'none');
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('#report-actions')).display`), 'none');
    if (width === 1280 && input === 'image') {
      const pdf = await send('Page.printToPDF', { preferCSSPageSize: true, printBackground: true, displayHeaderFooter: false });
      await writeFile(`test-results/${label}-report.pdf`, Buffer.from(pdf.data, 'base64'));
    }
    await send('Emulation.setEmulatedMedia', { media: 'screen' });
    await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
    const height = await evaluate(`Math.ceil(Math.max(document.documentElement.scrollHeight,document.body.scrollHeight))`);
    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true,
      clip: { x: 0, y: 0, width, height: height+128, scale: 1 } });
    await writeFile(`test-results/${label}-${input}-${width}.png`, Buffer.from(shot.data, 'base64'));
    const whitelist = /^(ECG Analyzer|Single-lead ECG signal measurement|Input|Choose file|Sample record|mitdb-\d+|synth-[a-z]+|Analyze|Calibration|Pixels per mm|Paper speed \(mm\/s\)|Gain \(mm\/mV\)|Crop \(left, top, right, bottom\)|Mains frequency \(Hz\)|50|60|Figure \d+\. .+\.|Table 1\. Measured values\.|Parameter\s+Value\s+Unit|Record duration|Sampling rate after resampling|R peaks detected|Mean heart rate|Minimum \/ maximum heart rate|Mean RR interval|SDNN|RMSSD|pNN50|RR coefficient of variation|Signal-to-noise ratio|Download JSON|Print|[-\d.na\/\s]+|s|Hz|bpm|ms|%|dB)$/;
    const outsideDeck = info.text.split(/[\n\t]/).map(x=>x.trim()).filter(Boolean).filter(line=>!whitelist.test(line) && !['Parameter','Value','Unit'].includes(line) && !info.notes.includes(line) && !line.startsWith('Signal quality below threshold:'));
    assert.deepEqual(outsideDeck, []);
    rows.push({ width, input, figures: info.figures, notes: info.notes, overflow: info.overflow, outsideDeck });
  }
}
const extra = [];
if (process.env.ECG_QA_LARGE_IMAGE) {
  const large = path.resolve(process.env.ECG_QA_LARGE_IMAGE);
  assert.ok((await stat(large)).size > 3_500_000);
  await send('Page.navigate', { url: 'http://127.0.0.1:3000/' });
  await until(`document.querySelector('#demo-select')?.options.length > 1`);
  await evaluate(`window.__qaFetch=window.fetch;window.fetch=async function(url,options){if(options?.body instanceof FormData){const f=options.body.get('image');window.__qaUpload={name:f.name,type:f.type,size:f.size,explain:options.body.get('explain')};}const response=await window.__qaFetch(url,options);if(String(url).endsWith('/analyze'))window.__qaReport=await response.clone().json();return response;}`);
  const root = await send('DOM.getDocument');
  const field = await send('DOM.querySelector', { nodeId: root.root.nodeId, selector: '#image-input' });
  await send('DOM.setFileInputFiles', { nodeId: field.nodeId, files: [large] });
  await until(`!document.querySelector('#analyze-button').disabled`);
  await evaluate(`document.querySelector('#analyze-button').click()`);
  await until(`!document.querySelector('#result-section').hidden && !document.querySelector('#analyze-button').disabled`);
  const upload = await evaluate(`window.__qaUpload`);
  const report = await evaluate(`({status:window.__qaReport.status, region:window.__qaReport.region_selection,hr:window.__qaReport.measurements.hr_mean_bpm})`);
  assert.equal(upload.name, path.basename(large)); assert.equal(upload.type, 'image/jpeg');
  assert.ok(upload.size <= 3_500_000); assert.equal(upload.explain, 'false'); assert.equal(report.status, 'ok');
  assert.ok(Math.max(...report.region.image_size) <= 3000); assert.ok(Math.abs(report.hr-72) <= 3);
  assert.equal(await evaluate(`document.querySelectorAll('.note').length`), 0);
  const text = await evaluate(`document.body.innerText`);
  assert.doesNotMatch(text, /\b(AI|screening|findings|possible|confidence|insight|powerful|seamless)\b/i);
  assert.equal(await evaluate(`document.documentElement.scrollWidth>innerWidth`), false);
  await writeFile(`test-results/${label}-resize-dom.txt`, text);
  await evaluate(`document.querySelector('#download-json').click()`);
  extra.push({ input: 'large image', originalBytes: (await stat(large)).size, upload, status: report.status, hr: report.hr });
}
if (label !== 'part-b') {
  if (process.env.ECG_QA_SHORT_IMAGE) {
    await send('Page.navigate', { url: 'http://127.0.0.1:3000/' });
    await until(`document.querySelector('#demo-select')?.options.length > 1`);
    const root = await send('DOM.getDocument');
    const field = await send('DOM.querySelector', { nodeId: root.root.nodeId, selector: '#image-input' });
    await send('DOM.setFileInputFiles', { nodeId: field.nodeId, files: [path.resolve(process.env.ECG_QA_SHORT_IMAGE)] });
    await until(`!document.querySelector('#analyze-button').disabled`);
    await evaluate(`document.querySelector('#analyze-button').click()`);
    await until(`!document.querySelector('#result-section').hidden && !document.querySelector('#analyze-button').disabled`);
    const state = await evaluate(`({notice:document.querySelector('.quality-notice')?.innerText,hr:document.querySelectorAll('tbody tr')[3]?.cells[1].innerText,notes:[...document.querySelectorAll('.note')].map(x=>x.innerText),table:!!document.querySelector('table'),text:document.body.innerText})`);
    assert.ok(state.notice?.startsWith('Signal quality below threshold:')); assert.equal(state.hr, 'n/a'); assert.equal(state.table, true);
    assert.equal(state.notes.length, 0);
    assert.doesNotMatch(state.text, /\b(AI|screening|findings|possible|confidence|insight|powerful|seamless)\b/i);
    await writeFile(`test-results/${label}-short-dom.txt`, state.text);
    extra.push({ input: 'short region', hr: state.hr, notes: state.notes, qualityNotice: state.notice });
  }
  if (process.env.ECG_QA_MANUAL_CROP) {
    const crop = process.env.ECG_QA_MANUAL_CROP.split(',').map(Number);
    await send('Page.navigate', { url: 'http://127.0.0.1:3000/' });
    await until(`document.querySelector('#demo-select')?.options.length > 1`);
    await evaluate(`window.__qaFetch=window.fetch;window.fetch=async function(url,options){const response=await window.__qaFetch(url,options);if(String(url).endsWith('/analyze'))window.__qaReport=await response.clone().json();return response;}`);
    const root = await send('DOM.getDocument');
    const field = await send('DOM.querySelector', { nodeId: root.root.nodeId, selector: '#image-input' });
    await send('DOM.setFileInputFiles', { nodeId: field.nodeId, files: [imagePath] });
    await until(`!document.querySelector('#analyze-button').disabled`);
    await evaluate(`document.querySelector('#crop-box').value=${JSON.stringify(crop.join(','))};document.querySelector('#analyze-button').click()`);
    await until(`!document.querySelector('#result-section').hidden && !document.querySelector('#analyze-button').disabled`);
    const region = await evaluate(`window.__qaReport.region_selection`);
    assert.equal(region.mode, 'manual'); assert.deepEqual(region.box, crop);
    assert.equal(await evaluate(`document.querySelectorAll('.note').length`), 0);
    extra.push({ input: 'manual region', box: region.box, mode: region.mode });
  }
  await send('Page.navigate', { url: 'http://127.0.0.1:3000/' });
  await until(`document.querySelector('#demo-select')?.options.length > 1`);
  // Submit a blank image through the same real form, without adding UI text.
  await evaluate(`(async()=>{const c=document.createElement('canvas');c.width=100;c.height=100;const ctx=c.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,100,100);const blob=await new Promise(r=>c.toBlob(r));const files=new DataTransfer();files.items.add(new File([blob],'blank.png',{type:'image/png'}));document.querySelector('#image-input').files=files.files;document.querySelector('#image-input').dispatchEvent(new Event('change'));})()`);
  await until(`!document.querySelector('#analyze-button').disabled`);
  await evaluate(`document.querySelector('#analyze-button').click()`);
  await until(`!document.querySelector('#result-section').hidden && !document.querySelector('#analyze-button').disabled`);
  assert.equal(await evaluate(`document.querySelector('#result').innerText`), 'No ECG trace detected in the image.');
  assert.equal(await evaluate(`document.querySelector('#report-actions').hidden`), true);
  extra.push({ input: 'blank image', result: 'No ECG trace detected in the image.' });
}
assert.deepEqual(errors, []);
for (const request of requests) {
  if (request.url.endsWith('/analyze-signal')) assert.equal(JSON.parse(request.postData).explain, false);
}
await writeFile(`test-results/${label}-qa.json`, JSON.stringify({ rows, extra, consoleErrors: errors, requests: requests.map(x=>({url:x.url, method:x.method})) }, null, 2));
console.log(JSON.stringify({ label, checks: rows.length+extra.length, consoleErrors: errors.length, rows, extra }, null, 2));
socket.close();
