// Overmark settings page: read the settings, render every control, save each change.
//
// Every save sends the whole settings object and the server answers with what it applied,
// so the page always shows what the running app holds. A refused save shows the server's
// reason and puts the controls back.

import { setSwitch } from '/static/_vendored/switch/switch.js';
import { showToast } from '/static/_vendored/toast/toast.js';
import { buildReadoutText } from '/static/_vendored/page-foot/page-foot.js';
import { initRestartSheet } from '/static/_vendored/page-foot/restart-sheet.js';
import { bindTextSize } from '/static/_vendored/text-size/text-size.js';

const $ = (id) => document.getElementById(id);
const APP = 'overmark'; // the localStorage prefix the boot script reads
const THEME_KEY = APP + '.theme';
const MODIFIERS = ['Control', 'Alt', 'Shift', 'Meta', 'OS'];
const NAMED_KEYS = { Space: 'space', Pause: 'pause', Insert: 'insert', Home: 'home', End: 'end' };

let settings = null; // the last settings the app confirmed
let choices = null;
let devices = { microphones: [], system_audio: [], screens: [] };

// ----- helpers ---------------------------------------------------------------------------

async function api(method, url, body) {
  const init = { method, cache: 'no-store', credentials: 'same-origin' };
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(url, init);
  let data = null;
  try { data = await res.json(); } catch (_) { data = null; }
  if (!res.ok) {
    const reason = data && (data.error || data.detail);
    throw new Error(typeof reason === 'string' ? reason : 'The app refused the change (' + res.status + ').');
  }
  return data;
}

function getPath(obj, path) {
  return path.split('.').reduce((node, key) => (node == null ? undefined : node[key]), obj);
}

function setPath(obj, path, value) {
  const keys = path.split('.');
  const last = keys.pop();
  keys.reduce((node, key) => node[key], obj)[last] = value;
}

function comboText(combo) {
  return combo ? combo.split('+').map((part) => part.length === 1 ? part.toUpperCase() : part[0].toUpperCase() + part.slice(1)).join(' + ') : '';
}

function fillSelect(select, options, current) {
  select.replaceChildren(...options.map(([value, label]) => {
    const option = document.createElement('option');
    option.value = String(value);
    option.textContent = label;
    return option;
  }));
  select.value = String(current);
}

function sheetToast(dialog) {
  return dialog ? dialog.querySelector('.sheet-toast') : null;
}

// Saves the settings `change` produces. Resolves true when the app applied it.
async function save(change, dialog) {
  const draft = structuredClone(settings);
  change(draft);
  try {
    const data = await api('PUT', '/api/settings', draft);
    settings = data.settings;
    render();
    showToast('Saved');
    return true;
  } catch (err) {
    render();
    showToast(err.message, 'error', { host: sheetToast(dialog) || undefined });
    return false;
  }
}

// ----- render ----------------------------------------------------------------------------

function screenOptions(current) {
  const options = [['all', 'All screens in one video'], ['active', 'Screen under the pointer']];
  devices.screens.forEach((label, i) => options.push([String(i + 1), label]));
  if (typeof current === 'number' && current > devices.screens.length) {
    options.push([String(current), 'Screen ' + current + ' (not connected)']);
  }
  return options;
}

function deviceOptions(list, current, emptyLabel) {
  const names = current && !list.includes(current) ? [current, ...list] : list;
  if (!names.length) return [['', emptyLabel]];
  return names.map((name) => [name, name]);
}

function renderPresets() {
  const list = $('presetList');
  list.replaceChildren(...settings.presets.map((preset, index) => {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'settings-row';
    row.setAttribute('aria-haspopup', 'dialog');
    row.dataset.track = 'settings.preset';
    const label = document.createElement('span');
    label.className = 'settings-row-label';
    label.textContent = (index + 1) + '  ' + preset.name;
    const value = document.createElement('span');
    value.className = 'settings-row-value';
    const swatch = document.createElement('span');
    swatch.className = 'preset-swatch';
    swatch.style.background = preset.color;
    value.append(swatch, preset.thickness_px + ' px');
    const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chevron.setAttribute('class', 'icon settings-row-chevron');
    chevron.setAttribute('aria-hidden', 'true');
    chevron.innerHTML = '<use href="#i-chevron-right"></use>';
    row.append(label, value, chevron);
    row.addEventListener('click', () => openPreset(index));
    return row;
  }));
}

function render() {
  if (!settings) return;
  document.querySelectorAll('.toggle[data-path]').forEach((btn) => setSwitch(btn, Boolean(getPath(settings, btn.dataset.path))));
  document.querySelectorAll('input[data-path]').forEach((input) => {
    if (document.activeElement !== input) input.value = getPath(settings, input.dataset.path);
  });
  document.querySelectorAll('[data-hotkey] .settings-row-value').forEach((el) => {
    el.textContent = comboText(settings.hotkey[el.parentElement.dataset.hotkey]);
  });
  document.querySelectorAll('[data-text]').forEach((row) => {
    const value = getPath(settings, row.dataset.text);
    const el = row.querySelector('.settings-row-value');
    el.textContent = value || row.dataset.placeholder || '';
    el.title = value || '';
  });

  const rec = settings.recording;
  fillSelect($('screenSelect'), screenOptions(rec.screen), rec.screen);
  fillSelect($('fpsSelect'), choices.frame_rates.map((fps) => [fps, fps + ' fps']), rec.frame_rate);
  fillSelect($('backendSelect'), choices.backends, rec.backend);
  fillSelect($('containerSelect'), choices.containers, rec.container);
  fillSelect($('qualitySelect'), choices.qualities, rec.quality);
  fillSelect($('awakeModeSelect'), choices.awake_modes, settings.keep_awake.mode);
  fillSelect($('micSelect'), deviceOptions(devices.microphones, rec.microphone.device, 'No microphone found'), rec.microphone.device);
  const outputs = devices.system_audio;
  const outputOptions = outputs.length ? [['', 'Default output'], ...deviceOptions(outputs, rec.system_audio.device, '')] : deviceOptions([], rec.system_audio.device, 'No output found');
  fillSelect($('systemAudioSelect'), outputOptions, rec.system_audio.device);

  $('micDeviceRow').hidden = !rec.microphone.enabled;
  $('systemAudioDeviceRow').hidden = !rec.system_audio.enabled;
  const noOutput = !outputs.length && !rec.system_audio.enabled;
  $('systemAudioSwitch').disabled = noOutput;
  $('systemAudioHint').textContent = noOutput ? 'No output device found' : 'What the computer plays';
  $('fadeDelayRow').hidden = !settings.fade.enabled;
  const nudge = settings.keep_awake.mode === 'nudge';
  $('awakeIntervalRow').hidden = !nudge;
  $('awakeDistanceRow').hidden = !nudge;
  renderPresets();
}

// ----- inline controls -------------------------------------------------------------------

function bindInline() {
  document.querySelectorAll('.toggle[data-path]').forEach((btn) => {
    btn.addEventListener('click', (event) => {
      event.preventDefault();
      const path = btn.dataset.path;
      const next = !getPath(settings, path);
      save((draft) => {
        setPath(draft, path, next);
        // Switching the microphone on picks the first one found, as the device list shows it.
        if (path === 'recording.microphone.enabled' && next && !draft.recording.microphone.device) {
          draft.recording.microphone.device = devices.microphones[0] || '';
        }
      });
    });
  });
  document.querySelectorAll('select[data-path]').forEach((select) => {
    select.addEventListener('change', () => {
      let value = select.value;
      if (select.dataset.kind === 'int') value = Number(value);
      if (select.dataset.kind === 'screen' && /^\d+$/.test(value)) value = Number(value);
      save((draft) => setPath(draft, select.dataset.path, value));
    });
  });
  document.querySelectorAll('input[data-path]').forEach((input) => {
    input.addEventListener('change', () => {
      const value = Number(input.value);
      const low = input.min === '' ? -Infinity : Number(input.min);
      const high = input.max === '' ? Infinity : Number(input.max);
      const whole = input.dataset.whole === 'true';
      if (input.value === '' || Number.isNaN(value) || value < low || value > high || (whole && !Number.isInteger(value))) {
        const range = high === Infinity ? low + ' or more' : 'from ' + low + ' to ' + high;
        showToast(input.dataset.what + ' must be ' + (whole ? 'a whole number ' : '') + range + '.', 'error');
        render();
        return;
      }
      save((draft) => setPath(draft, input.dataset.path, value));
    });
  });
}

// ----- sheets ----------------------------------------------------------------------------

function wireClose(dialog) {
  dialog.querySelectorAll('[data-close]').forEach((btn) => btn.addEventListener('click', () => dialog.close()));
}

function openText(row) {
  const dialog = $('textSheet');
  const input = $('textSheetInput');
  const path = row.dataset.text;
  $('textSheetTitle').textContent = row.dataset.title;
  input.value = getPath(settings, path) || '';
  input.placeholder = row.dataset.placeholder || '';
  $('textSheetHint').textContent = row.dataset.tokens === 'true'
    ? 'Tokens: ' + choices.name_tokens.map((t) => '{' + t + '}').join(', ') + '.'
    : (row.dataset.placeholder ? 'Empty: ' + row.dataset.placeholder + '.' : '');
  $('textSheetBrowse').hidden = row.dataset.browse !== 'true';
  dialog.dataset.path = path;
  dialog.showModal();
}

async function textDone() {
  const dialog = $('textSheet');
  const path = dialog.dataset.path;
  const value = $('textSheetInput').value.trim();
  if (value === (getPath(settings, path) || '')) { dialog.close(); return; }
  if (await save((draft) => setPath(draft, path, value), dialog)) {
    dialog.close();
    if (path === 'recording.ffmpeg_path') loadDevices();
  }
}

async function browseFolder() {
  const button = $('textSheetBrowse');
  button.setAttribute('aria-busy', 'true');
  button.disabled = true;
  try {
    const data = await api('POST', '/api/pick-folder', { start: $('textSheetInput').value.trim() });
    if (data.folder) $('textSheetInput').value = data.folder;
  } catch (err) {
    showToast(err.message, 'error', { host: sheetToast($('textSheet')) });
  } finally {
    button.removeAttribute('aria-busy');
    button.disabled = false;
  }
}

let pendingCombo = '';

function openHotkey(row) {
  const dialog = $('hotkeySheet');
  dialog.dataset.key = row.dataset.hotkey;
  $('hotkeySheetTitle').textContent = row.dataset.title;
  pendingCombo = settings.hotkey[row.dataset.hotkey];
  $('hotkeyCapture').value = comboText(pendingCombo);
  dialog.showModal();
  $('hotkeyCapture').focus();
}

// The combination a key press makes, in config.json's spelling, or '' for a modifier alone.
function comboFromEvent(event) {
  if (MODIFIERS.includes(event.key)) return '';
  let key;
  if (/^Key[A-Z]$/.test(event.code)) key = event.code.slice(3).toLowerCase();
  else if (/^Digit\d$/.test(event.code)) key = event.code.slice(5);
  else if (/^F\d{1,2}$/.test(event.code)) key = event.code.toLowerCase();
  else key = NAMED_KEYS[event.code] || event.key.toLowerCase();
  const mods = [];
  if (event.ctrlKey) mods.push('ctrl');
  if (event.altKey) mods.push('alt');
  if (event.shiftKey) mods.push('shift');
  if (event.metaKey) mods.push('win');
  return [...mods, key].join('+');
}

function captureKey(event) {
  const plain = !event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey;
  if (plain && (event.key === 'Escape' || event.key === 'Tab' || event.key === 'Enter')) return;
  event.preventDefault();
  const combo = comboFromEvent(event);
  if (!combo) return;
  pendingCombo = combo;
  $('hotkeyCapture').value = comboText(combo);
}

async function hotkeyDone() {
  const dialog = $('hotkeySheet');
  const key = dialog.dataset.key;
  if (pendingCombo === settings.hotkey[key]) { dialog.close(); return; }
  if (await save((draft) => { draft.hotkey[key] = pendingCombo; }, dialog)) dialog.close();
}

function syncPresetRows() {
  $('presetPercentRow').hidden = $('presetTransparent').getAttribute('aria-checked') !== 'true';
  $('presetOutlineRow').hidden = $('presetOutline').getAttribute('aria-checked') !== 'true';
}

function openPreset(index) {
  const dialog = $('presetSheet');
  const preset = settings.presets[index];
  dialog.dataset.index = String(index);
  $('presetSheetTitle').textContent = 'Preset ' + (index + 1);
  $('presetName').value = preset.name;
  $('presetColor').value = preset.color.toLowerCase();
  $('presetThickness').value = preset.thickness_px;
  $('presetPercent').max = String(choices.max_transparency);
  $('presetPercent').value = preset.transparency.percent;
  setSwitch($('presetTransparent'), preset.transparency.enabled);
  $('presetOutlinePx').value = preset.outline.thickness_px;
  setSwitch($('presetOutline'), preset.outline.enabled);
  syncPresetRows();
  dialog.showModal();
}

function numberIn(id, what, low, high) {
  const value = Number($(id).value);
  if ($(id).value === '' || Number.isNaN(value) || value < low || value > high) {
    throw new Error(what + ' must be from ' + low + ' to ' + high + '.');
  }
  return value;
}

async function presetDone() {
  const dialog = $('presetSheet');
  const index = Number(dialog.dataset.index);
  let preset;
  try {
    preset = {
      name: $('presetName').value.trim() || settings.presets[index].name,
      color: $('presetColor').value.toUpperCase(),
      thickness_px: numberIn('presetThickness', 'Thickness', 1, 120),
      transparency: {
        enabled: $('presetTransparent').getAttribute('aria-checked') === 'true',
        percent: Math.round(numberIn('presetPercent', 'Transparency', 0, choices.max_transparency)),
      },
      outline: {
        enabled: $('presetOutline').getAttribute('aria-checked') === 'true',
        thickness_px: numberIn('presetOutlinePx', 'Outline', 0, 12),
      },
    };
  } catch (err) {
    showToast(err.message, 'error', { host: sheetToast(dialog) });
    return;
  }
  if (await save((draft) => { draft.presets[index] = preset; }, dialog)) dialog.close();
}

function openKeys() {
  const rows = Object.entries(settings.keys).map(([action, combo]) => {
    const row = document.createElement('div');
    row.className = 'row';
    const label = document.createElement('span');
    label.textContent = choices.key_labels[action] || action;
    const value = document.createElement('kbd');
    value.textContent = comboText(combo);
    row.append(label, value);
    return row;
  });
  const note = document.createElement('p');
  note.className = 'sheet-hint';
  note.textContent = 'These keys work only while drawing. They are set in config.json.';
  $('keysList').replaceChildren(...rows, note);
  $('keysSheet').showModal();
}

function bindSheets() {
  ['textSheet', 'hotkeySheet', 'presetSheet', 'keysSheet'].forEach((id) => wireClose($(id)));
  document.querySelectorAll('[data-text]').forEach((row) => row.addEventListener('click', () => openText(row)));
  document.querySelectorAll('[data-hotkey]').forEach((row) => row.addEventListener('click', () => openHotkey(row)));
  $('keysRow').addEventListener('click', openKeys);
  $('textSheetDone').addEventListener('click', textDone);
  $('textSheetInput').addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); textDone(); } });
  $('textSheetBrowse').addEventListener('click', browseFolder);
  $('hotkeyCapture').addEventListener('keydown', captureKey);
  $('hotkeySheetDone').addEventListener('click', hotkeyDone);
  $('presetSheetDone').addEventListener('click', presetDone);
  ['presetTransparent', 'presetOutline'].forEach((id) => {
    $(id).addEventListener('click', (event) => {
      event.preventDefault();
      setSwitch($(id), $(id).getAttribute('aria-checked') !== 'true');
      syncPresetRows();
    });
  });
}

// ----- theme, build line, start ----------------------------------------------------------

function showTheme() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const toggle = $('themeToggle');
  toggle.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
  toggle.querySelector('use').setAttribute('href', dark ? '#i-sun' : '#i-moon');
}

function bindTheme() {
  showTheme();
  $('themeToggle').addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem(THEME_KEY, next); } catch (_) { /* a private window keeps it for this visit */ }
    showTheme();
  });
}

async function loadVersion() {
  try {
    const body = await api('GET', '/api/version');
    $('buildReadout').textContent = buildReadoutText(body.git_sha || 'unknown', body.built_at || '');
    $('aboutBuild').textContent = body.git_sha ? body.git_sha.slice(0, 7) : 'unknown';
  } catch (_) {
    $('buildReadout').textContent = '';
    $('aboutBuild').textContent = 'unknown';
  }
  initRestartSheet();
}

async function loadDevices() {
  try {
    const query = '?ffmpeg_path=' + encodeURIComponent(settings.recording.ffmpeg_path || '');
    devices = await api('GET', '/api/devices' + query);
    render();
  } catch (err) {
    showToast('Could not list screens and audio devices: ' + err.message, 'error');
  }
}

async function start() {
  bindTheme();
  bindTextSize($('textSizeControl'), APP);
  bindInline();
  bindSheets();
  // The page is the app's only view: Esc must not close it.
  $('settingsPage').addEventListener('cancel', (event) => event.preventDefault());
  try {
    const data = await api('GET', '/api/settings');
    settings = data.settings;
    choices = data.choices;
    $('awakeInterval').min = String(choices.min_interval_s);
    $('awakeInterval').max = String(choices.max_interval_s);
    $('awakeDistance').max = String(choices.max_distance_px);
    $('bitrateInput').max = String(choices.max_bitrate_kbps);
    render();
  } catch (err) {
    showToast('Could not read the settings: ' + err.message, 'error', { ms: 0 });
  }
  $('settingsBody').removeAttribute('aria-busy');
  loadVersion();
  if (settings) loadDevices();
}

start();
