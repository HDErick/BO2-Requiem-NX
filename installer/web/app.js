// BO2 Requiem Compressor: installs Black Ops II for Android or the Nintendo Switch from a PC copy.
// Runs entirely in the browser (GitHub Pages or any static server). Game files are read in place;
// image packs and sound banks are packed by t6pack (WebAssembly, web/generated) in Web Workers
// (worker.js) through the origin's private storage, and every result is streamed to the chosen
// folder or into a ZIP. Nothing is uploaded. The text is in English, Portuguese or Spanish (i18n.mjs),
// chosen on the first screen.
import { ZipWriter } from './zip-writer.mjs';
import { LANGUAGES, language, setLanguage, t } from './i18n.mjs';

const $ = id => document.getElementById(id);
const MANIFEST = '.t6installer.json';
const ZSTD_LEVEL = '15';   // within 0.3% of level 19 on image packs, twice as fast
// Where the game goes inside the folder or the ZIP.
const TARGETS = {
  android: { root: ['BO2'], label: 'Android' },
  switch: { root: ['switch', 't6game'], label: 'Nintendo Switch' },
};
// t6pack arguments per level and kind ($IN / $OUT are filled in by worker.js); null = copied.
const LEVELS = {
  lossless: { ipak: ['ipak', '$IN', '$OUT', '--cap', '0'], sabs: null, sabl: ['pack', '$IN', '$OUT'] },
  medium: { ipak: ['ipak', '$IN', '$OUT', '--cap', '512'], sabs: ['bank', '$IN', '$OUT', '--profile', 'medium'],
            sabl: ['bank', '$IN', '$OUT', '--profile', 'medium', '--container'] },
  maximum: { ipak: ['ipak', '$IN', '$OUT', '--cap', '256'], sabs: ['bank', '$IN', '$OUT', '--profile', 'maximum'],
             sabl: ['bank', '$IN', '$OUT', '--profile', 'maximum', '--container'] },
};
// Output size as a share of the input, from complete installs of the retail PC game (COMPRESSOR.md).
const RATIOS = {
  lossless: { ipak: 0.835, sabs: 1, sabl: 0.83 },
  medium: { ipak: 0.526, sabs: 0.706, sabl: 0.697 },
  maximum: { ipak: 0.186, sabs: 0.346, sabl: 0.391 },
};
const SKIP = /\.(log|dmp|mdmp|part|tmp)$/i;
const ORDER = ['lossless', 'medium', 'maximum'];   // weakest to strongest
const T6ZB = 0x425a3654;   // a T6ZB container's first 4 bytes, little-endian ("T6ZB", nx/common/t6z_format.h)

// The game modes, told apart by file name (the retail PC layout; checked against a complete Steam copy and a
// Multiplayer + Zombies one). A mode is installed when its main zone is there; the files no mode claims
// (base.ipak, so.ipak, the dlc packs, weapons, code_pre_gfx, the shared sound and videos, main/) always go.
// Each zone loads only the image pack of its own name, so leaving a mode out never takes anything another
// mode reads. BO2 Requiem plays Zombies and Multiplayer; Campaign is off by default.
const MODES = {
  zm: { core: 'zone/all/common_zm.ff' },   // names and descriptions: i18n.mjs, mode.zm / mode.zm.what
  mp: { core: 'zone/all/common_mp.ff' },
  sp: { core: 'zone/all/frontend.ff' },
};
const SP_ZONE = /^(afghanistan|angola|blackout|haiti|karma|la_1|la_1b|la_2|monsoon|nicaragua|pakistan|panama|yemen|frontend)(_|$)|^so_(cmp|rts|tut)_|^su_|^(sp|common|patch|weapon_attach_shared)$/;
const SP_VIDEO = /^(a[1-3]_|b[1-3]_|c[1-3]_|a7x|afghanistan|angola|blackout|haiti|karma|la_|monsoon|nicaragua|pakistan|panama|yemen|frontend_load|so_|strike_force|vtol_outro|crc_part|eye_v5|generalstore|sam_gizmos|spider_bootup|prologue)/;

// 'zm', 'mp', 'sp', or null for a file every mode uses.
function modeOf(rel) {
  const parts = rel.toLowerCase().split('/');
  const file = parts.at(-1);
  if (parts.length === 1) return { 'localization.txt': 'sp', 'localization_mp.txt': 'mp', 'localization_zm.txt': 'zm' }[file] || null;
  if (parts[0] === 'video') return file.startsWith('zm_') ? 'zm' : file.startsWith('mp_') ? 'mp' : SP_VIDEO.test(file) ? 'sp' : null;
  if (parts[0] === 'sound')
    return file.startsWith('zmb_') ? 'zm' : file.startsWith('mpl_') ? 'mp' : /^(spl_|so_(cmp|rts|tut)_)/.test(file) ? 'sp' : null;
  if (parts[0] !== 'zone' || parts.length !== 3) return null;
  let name = file.replace(/\.[^.]+$/, '');
  if (parts[1] !== 'all') name = name.replace(/^[a-z]{2}_/, '');   // zone/english/en_mp_la.ff: mp_la
  if (SP_ZONE.test(name)) return 'sp';
  if (/^zm$|^zm_|_zm$|^so_z|^dlczm/.test(name)) return 'zm';
  if (/^mp$|^mp_|_mp$|^faction_/.test(name)) return 'mp';
  return null;
}

const canPickFolders = typeof showDirectoryPicker === 'function';
const canSaveFile = typeof showSaveFilePicker === 'function';
const canStreamDownload = 'serviceWorker' in navigator && typeof ReadableStream === 'function';
const hasPrivateStorage = !!(navigator.storage && navigator.storage.getDirectory);

let entries = null;      // [{ rel, size, modified, getFile, mode }]
let modes = null;        // per mode: { files, bytes, installed }
const chosen = new Set();   // the modes to install
let sourceHandle = null;
let sourceName = '';
let release = null;      // the Switch executables published with the site: { tag, name, files: [{ name, size }] }
let run = null;          // the running install

if (canStreamDownload) navigator.serviceWorker.register('./sw.js').catch(() => {});

const gb = n => (n / 1e9).toFixed(n >= 1e10 ? 1 : 2) + ' GB';
const minutes = s => s < 90 ? Math.round(s) + ' s' : Math.round(s / 60) + ' min';
const level = () => document.querySelector('input[name=level]:checked').value;
const target = () => document.querySelector('input[name=target]:checked').value;
const selected = () => entries.filter(e => !e.mode || chosen.has(e.mode));
const playable = () => chosen.has('zm') || chosen.has('mp');
const modeNames = list => Object.keys(MODES).filter(m => list.includes(m)).map(m => t(`mode.${m}`)).join(', ');
const levelName = lv => t(`level.${lv}`).toUpperCase();
const sizeText = n => n < 1e9 ? Math.max(1, Math.round(n / 1e6)) + ' MB' : gb(n);

// The latest BO2 Requiem release's NROs, copied next to the page when it is published
// (fetch_release.py): GitHub's release downloads cannot be read from another origin.
async function loadRelease() {
  try {
    const response = await fetch('./release/release.json', { cache: 'no-cache' });
    if (!response.ok) throw new Error(response.statusText);
    release = await response.json();
    if (!release.files || !release.files.length) throw new Error('no executables');
  } catch {
    release = null;
  }
  showRelease();
  updateButtons();
}

function showRelease() {
  $('release-note').textContent = release ? t('release.ok', { name: release.name || release.tag }) : t('release.missing');
  $('release-note').className = release ? '' : 'warn';
}

function kindOf(rel) {
  const lower = rel.toLowerCase();
  if (lower.startsWith('zone/') && lower.endsWith('.ipak')) return 'ipak';
  if (lower.startsWith('sound/') && lower.endsWith('.sabs')) return 'sabs';
  if (lower.startsWith('sound/') && lower.endsWith('.sabl')) return 'sabl';
  return 'copy';
}

// What the game needs from a PC folder: zone, sound, video, main (no logs), localization*.txt.
function wanted(parts) {
  const top = parts[0].toLowerCase();
  if (parts.length === 1) return /^localization.*\.txt$/i.test(parts[0]);
  if (!['zone', 'sound', 'video', 'main'].includes(top)) return false;
  if (parts.some(p => p.toLowerCase() === 'logs')) return false;
  return !SKIP.test(parts.at(-1));
}

async function listFolder(dir, path, out) {
  for await (const [name, handle] of dir.entries()) {
    const parts = [...path, name];
    if (handle.kind === 'directory') {
      if (path.length || ['zone', 'sound', 'video', 'main'].includes(name.toLowerCase())) await listFolder(handle, parts, out);
    } else if (wanted(parts)) {
      const file = await handle.getFile();
      out.push({ rel: parts.join('/'), size: file.size, modified: file.lastModified, getFile: () => handle.getFile() });
    }
  }
  return out;
}

function checkSource(list) {
  if (!list.some(e => e.rel.toLowerCase().startsWith('zone/all/')) || !list.some(e => e.rel.toLowerCase().startsWith('sound/')))
    throw new Error(t('source.bad'));
  for (const e of list) e.mode = modeOf(e.rel);
  return list.sort((a, b) => a.rel.localeCompare(b.rel));
}

// Files this installer compressed already (the folder is one it installed to, or an extracted ZIP of it).
// e.packed: the level from the folder's .t6installer.json (when the file is the size it wrote), 'unknown'
// for a T6ZB container it does not describe, null for a game file as it ships. A streamed sound bank
// re-encoded at MEDIUM or MAXIMUM is a plain bank again, so only the manifest tells it apart.
async function findPacked(list, manifest) {
  const files = (manifest && manifest.files) || {};
  await Promise.all(list.map(async e => {
    e.packed = null;
    if (kindOf(e.rel) === 'copy') return;
    const old = files[e.rel];
    const lv = old && old.out === e.size ? String(old.key).split('|')[0] : null;
    if (ORDER.includes(lv)) { e.packed = lv; return; }
    try {
      const head = new DataView(await (await e.getFile()).slice(0, 4).arrayBuffer());
      if (head.byteLength === 4 && head.getUint32(0, true) === T6ZB) e.packed = 'unknown';
    } catch {}
  }));
  return list;
}

async function readJson(file) {
  try { return JSON.parse(await file.text()); } catch { return null; }
}

// What a file gets at level lv: its t6pack arguments, or null to copy it. A file compressed already is
// copied, unless its level is known and weaker than lv: then it is packed again from that file (t6pack
// reads its own containers). A weaker level cannot bring back what a stronger one took out.
function argsFor(e, lv) {
  const kind = kindOf(e.rel);
  if (kind === 'copy') return null;
  if (e.packed && (e.packed === 'unknown' || ORDER.indexOf(lv) <= ORDER.indexOf(e.packed))) return null;
  return LEVELS[lv][kind];
}

// A file's estimated size at level lv.
function estimate(e, lv) {
  const kind = kindOf(e.rel);
  if (!argsFor(e, lv)) return e.size;
  return e.size * RATIOS[lv][kind] / (e.packed ? RATIOS[e.packed][kind] : 1);
}

// Which modes the folder has, and the checkboxes for them: installed modes on (Campaign off), leftovers of a
// mode without its main zone (the English campaign zones of a Multiplayer + Zombies copy) off.
function findModes() {
  modes = {};
  for (const m of Object.keys(MODES)) modes[m] = { files: 0, bytes: 0, installed: false };
  for (const e of entries) {
    if (e.mode) { modes[e.mode].files++; modes[e.mode].bytes += e.size; }
    for (const m of Object.keys(MODES)) if (e.rel.toLowerCase() === MODES[m].core) modes[m].installed = true;
  }
  chosen.clear();
  for (const m of Object.keys(MODES)) {
    const box = document.querySelector(`input[name=mode][value=${m}]`);
    const info = modes[m];
    box.closest('.choice').hidden = !info.files;
    box.checked = info.installed && m !== 'sp';
    if (box.checked) chosen.add(m);
  }
  $('modes').hidden = !Object.values(modes).some(i => i.files);
  showModes();
}

function showModes() {
  for (const m of Object.keys(MODES)) {
    const info = modes[m];
    $(`mode-size-${m}`).textContent = sizeText(info.bytes);
    $(`mode-what-${m}`).textContent = info.installed ? t(`mode.${m}.what`) : t('mode.leftover', { n: info.files });
  }
}

function status(text) {
  $('result').hidden = false;
  $('status').textContent = text;
}

function updateButtons() {
  const ready = !!entries && !run && (target() !== 'switch' || !!release) && playable();
  $('install').disabled = !ready || !canPickFolders || !hasPrivateStorage;
  $('zip').disabled = !ready || !(canSaveFile || canStreamDownload) || !hasPrivateStorage;
  $('install').title = !canPickFolders ? t('needs.chrome') : '';
  $('change-language').disabled = !!run;
  if (!hasPrivateStorage) $('summary').textContent = t('needs.opfs');
  else summary();
}

function showSource(name) {
  sourceName = name;
  findModes();
  showSourceLabel();
  showSizes();
}

function showSourceLabel() {
  const total = entries.reduce((a, e) => a + e.size, 0);
  const found = Object.keys(MODES).filter(m => modes[m].installed);
  const packed = entries.filter(e => e.packed).length;
  $('source-label').textContent = t('source.label', { name: sourceName, files: entries.length, size: gb(total) }) +
    (found.length ? t('source.modes', { modes: modeNames(found) }) : t('source.nomode')) +
    (packed ? t('source.packed', { n: packed }) : '');
}

// The levels' estimates, for the chosen modes.
function showSizes() {
  const list = selected();
  for (const el of document.querySelectorAll('[data-size]'))
    el.textContent = t('size.about', { size: gb(list.reduce((a, e) => a + estimate(e, el.dataset.size), 0)) });
}

function summary() {
  if (run) return;
  if (!entries) {
    $('summary').textContent = t('summary.idle');
    return;
  }
  if (target() === 'switch' && !release) {
    $('summary').textContent = t('summary.noswitch');
    return;
  }
  if (!playable()) {
    $('summary').textContent = modes && (modes.zm.installed || modes.mp.installed) ? t('summary.choose') : t('summary.nomodes');
    return;
  }
  const list = selected();
  const total = list.reduce((a, e) => a + e.size, 0);
  const el = document.querySelector(`[data-size=${level()}]`);
  const where = TARGETS[target()].root.join('/') + '/';
  $('summary').textContent = t('summary.plan', { modes: modeNames([...chosen]), files: list.length, size: gb(total),
    out: el.textContent, where, target: TARGETS[target()].label });
}

async function pickSource() {
  if (!canPickFolders) { $('source-files').click(); return; }
  try {
    const dir = await showDirectoryPicker({ id: 't6-source', mode: 'read' });
    $('source-label').textContent = t('source.reading');
    const list = checkSource(await listFolder(dir, [], []));
    const manifest = await dir.getFileHandle(MANIFEST).then(h => h.getFile()).then(readJson, () => null);
    entries = await findPacked(list, manifest);
    sourceHandle = dir;
    showSource(dir.name);
  } catch (error) {
    if (error.name !== 'AbortError') { entries = null; $('source-label').textContent = error.message; }
  }
  updateButtons();
}

$('source-files').addEventListener('change', async () => {
  try {
    const files = [...$('source-files').files];
    if (!files.length) return;
    const list = [];
    let manifest = null;
    for (const file of files) {
      const parts = file.webkitRelativePath.split('/').slice(1);   // drop the chosen folder's name
      if (parts.length === 1 && parts[0] === MANIFEST) manifest = await readJson(file);
      else if (parts.length && wanted(parts)) list.push({ rel: parts.join('/'), size: file.size, modified: file.lastModified, getFile: async () => file });
    }
    $('source-label').textContent = t('source.reading');
    entries = await findPacked(checkSource(list), manifest);
    sourceHandle = null;
    showSource(files[0].webkitRelativePath.split('/')[0]);
  } catch (error) {
    entries = null;
    $('source-label').textContent = error.message;
  }
  updateButtons();
});

// ---- where the install goes ---------------------------------------------------------------
function counting(onBytes, isCancelled) {
  return new TransformStream({
    transform(chunk, controller) {
      if (isCancelled()) throw new DOMException('Cancelled.', 'AbortError');
      onBytes(chunk.byteLength);
      controller.enqueue(chunk);
    },
  });
}

async function folderSink(root, prefix) {
  let base = root;
  for (const p of prefix) base = await base.getDirectoryHandle(p, { create: true });
  const dirs = new Map();
  const dirOf = async parts => {
    let dir = base, key = '';
    for (const p of parts) {
      key += '/' + p;
      if (!dirs.has(key)) dirs.set(key, await dir.getDirectoryHandle(p, { create: true }));
      dir = dirs.get(key);
    }
    return dir;
  };
  return {
    async existing(rel) {
      try {
        const parts = rel.split('/');
        const file = await (await (await dirOf(parts.slice(0, -1))).getFileHandle(parts.at(-1))).getFile();
        return file.size;
      } catch { return -1; }
    },
    async save(rel, stream) {
      const parts = rel.split('/');
      const handle = await (await dirOf(parts.slice(0, -1))).getFileHandle(parts.at(-1), { create: true });
      await stream.pipeTo(await handle.createWritable());
    },
    async readManifest() {
      try { return JSON.parse(await (await (await base.getFileHandle(MANIFEST)).getFile()).text()); } catch { return null; }
    },
    async writeManifest(m) {
      const w = await (await base.getFileHandle(MANIFEST, { create: true })).createWritable();
      await w.write(JSON.stringify(m));
      await w.close();
    },
    async close() {},
  };
}

// The manifest goes in last, so an extracted ZIP tells later installs what it holds (findPacked).
function zipSink(writable, prefix) {
  const zip = new ZipWriter(writable);
  const base = prefix.join('/') + '/';
  let manifest = null;
  return {
    existing: async () => -1,
    save: (rel, stream) => zip.add(base + rel, stream),
    readManifest: async () => null,
    writeManifest: async m => { manifest = m; },
    async close() {
      if (manifest) await zip.add(base + MANIFEST, new Blob([JSON.stringify(manifest)]).stream());
      await zip.close();
    },
  };
}

// A writable that feeds sw.js, which serves it as a normal download (Firefox, Safari).
async function serviceWorkerWritable(name) {
  const registration = await navigator.serviceWorker.ready;
  const worker = registration.active;
  if (!worker) throw new Error(t('error.helper'));
  const channel = new MessageChannel();
  const port = channel.port1;
  let credits = 0, cancelled = false, wake = null;
  const ready = new Promise(resolve => {
    port.onmessage = ({ data }) => {
      if (data.type === 'ready') resolve();
      else if (data.type === 'pull') credits++;
      else if (data.type === 'cancel') cancelled = true;
      if (wake) { const w = wake; wake = null; w(); }
    };
  });
  const id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);
  worker.postMessage({ type: 'download', id, name }, [channel.port2]);
  await ready;
  const keepAlive = setInterval(() => worker.postMessage({ type: 'ping' }), 10000);
  const frame = document.createElement('iframe');
  frame.hidden = true;
  frame.src = `./download/${id}/${encodeURIComponent(name)}`;
  document.body.append(frame);
  const CHUNK = 1 << 20;
  let buffer = new Uint8Array(CHUNK), used = 0;
  const flush = async () => {
    if (!used) return;
    while (!credits && !cancelled) await new Promise(resolve => { wake = resolve; });
    if (cancelled) throw new DOMException('The download was cancelled.', 'AbortError');
    credits--;
    const chunk = buffer.slice(0, used);
    port.postMessage({ type: 'chunk', chunk: chunk.buffer }, [chunk.buffer]);
    used = 0;
  };
  return {
    async write(bytes) {
      for (let at = 0; at < bytes.length;) {
        const n = Math.min(CHUNK - used, bytes.length - at);
        buffer.set(bytes.subarray(at, at + n), used);
        used += n; at += n;
        if (used === CHUNK) await flush();
      }
    },
    async close() {
      await flush();
      port.postMessage({ type: 'close' });
      clearInterval(keepAlive);
      setTimeout(() => frame.remove(), 60000);
    },
  };
}

// ---- the install ----------------------------------------------------------------------------
function workerCount() {
  const cores = navigator.hardwareConcurrency || 4;
  const memory = navigator.deviceMemory || 8;   // GB, Chrome only
  return Math.max(1, Math.min(6, cores - 1, Math.floor(memory / 1.5)));
}

async function clearTemp() {
  const root = await navigator.storage.getDirectory();
  await root.removeEntry('t6pack-tmp', { recursive: true }).catch(() => {});
}

async function install(toZip) {
  const lv = level();
  const tg = target();
  const prefix = TARGETS[tg].root;
  let sink;
  try {
    if (tg === 'switch' && !release) throw new Error(t('error.noswitch'));
    if (toZip) {
      const name = `BO2-Requiem-${tg === 'switch' ? 'Switch' : 'Android'}-${lv}.zip`;
      const writable = canSaveFile
        ? await (await showSaveFilePicker({ id: 't6-zip', suggestedName: name, types: [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }] })).createWritable()
        : await serviceWorkerWritable(name);
      sink = zipSink(writable, prefix);
    } else {
      const root = await showDirectoryPicker({ id: 't6-dest', mode: 'readwrite' });
      if (sourceHandle && ((await sourceHandle.resolve(root)) !== null || (await root.resolve(sourceHandle)) !== null))
        throw new Error(t('error.outside'));
      sink = await folderSink(root, prefix);
    }
  } catch (error) {
    if (error.name !== 'AbortError') status(error.message);
    return;
  }

  const started = performance.now();
  const r = run = { cancelled: false, workers: [], log: [], read: 0, written: 0, current: new Set() };
  for (const el of [$('source'), $('modes'), $('levels'), $('targets'), $('install'), $('zip')]) el.disabled = true;
  $('cancel').hidden = false;
  $('log').replaceChildren();
  status(t('run.start', { target: TARGETS[tg].label, level: levelName(lv) }));
  const note = text => {
    r.log.push(text);
    const li = document.createElement('li');
    li.textContent = text;
    $('log').append(li);
  };

  const manifest = (await sink.readManifest()) || { version: 1, files: {} };
  for (const m of Object.keys(MODES))
    if (modes[m].files && !chosen.has(m)) note(t('note.leftout', { mode: t(`mode.${m}`), files: modes[m].files, size: sizeText(modes[m].bytes) }));
  const stale = Object.keys(manifest.files).filter(rel => { const m = modeOf(rel); return m && !chosen.has(m); });
  if (stale.length)
    note(t('note.stale', { n: stale.length, modes: modeNames([...new Set(stale.map(modeOf))]) }));
  // Files compressed already: copied, or packed again when their level is weaker than this one.
  const already = selected().filter(e => e.packed);
  const again = already.filter(e => argsFor(e, lv)).length;
  const stronger = already.filter(e => e.packed !== 'unknown' && ORDER.indexOf(e.packed) > ORDER.indexOf(lv));
  if (already.length - again) note(t('note.packed', { n: already.length - again }));
  if (again) note(t('note.repacked', { n: again, level: levelName(lv) }));
  if (stronger.length)
    note(t('note.stronger', { n: stronger.length, levels: [...new Set(stronger.map(e => levelName(e.packed)))].join(', ') }));
  const jobs = [];
  for (const e of selected()) {
    const kind = kindOf(e.rel);
    const args = argsFor(e, lv);
    // The first field is what the output holds (findPacked reads it back): the level it was packed at,
    // 'copy' for a game file as it ships, 'packed' for a container of unknown level.
    const content = args ? lv : !e.packed ? 'copy' : e.packed === 'unknown' ? 'packed' : e.packed;
    const key = `${content}|${(args || []).join(' ')}|${e.size}|${e.modified}`;
    const job = { ...e, kind, args, key, progress: 0, sunk: 0, state: 'waiting' };
    if (e.packed && !args) job.method = t('note.already');
    const old = manifest.files[e.rel];
    if (old && old.key === key && (await sink.existing(e.rel)) === old.out) {
      job.state = 'kept';
      r.read += e.size;
      r.written += old.out;
    }
    jobs.push(job);
  }
  if (tg === 'switch') {
    // The release's executables: always written, so an install picks up a newer release.
    for (const f of release.files) {
      jobs.push({
        rel: f.name, size: f.size, kind: 'copy', args: null, key: 'nro', progress: 0, sunk: 0, state: 'waiting',
        getFile: async () => {
          const response = await fetch('./release/' + encodeURIComponent(f.name), { cache: 'no-cache' });
          if (!response.ok) throw new Error(t('error.nro', { name: f.name, status: response.status }));
          return response.blob();
        },
      });
    }
  }
  const total = jobs.reduce((a, j) => a + j.size, 0);
  const kept = jobs.filter(j => j.state === 'kept').length;
  if (kept) note(t('note.kept', { n: kept }));

  // Copied files are ready at once; packed ones when their worker finishes (placed first, to free
  // the private storage they take).
  const ready = jobs.filter(j => j.state === 'waiting' && !j.args);
  const packQueue = jobs.filter(j => j.state === 'waiting' && j.args).sort((a, b) => b.size - a.size);
  let toSink = jobs.filter(j => j.state === 'waiting').length;
  let wakeSink = null;
  const pushReady = (job, first) => {
    if (first) ready.unshift(job); else ready.push(job);
    if (wakeSink) { const w = wakeSink; wakeSink = null; w(); }
  };
  let tmpDir = null;
  let failure = null;

  const timer = setInterval(() => {
    let done = 0;
    for (const j of jobs) {
      if (j.state === 'kept' || j.state === 'written') done += j.size;
      else if (j.args) done += j.size * (0.85 * j.progress + 0.15 * (j.output ? j.sunk / Math.max(1, j.outSize) : 0));
      else done += j.sunk;
    }
    const fraction = total ? done / total : 1;
    const elapsed = (performance.now() - started) / 1000;
    $('progress').value = fraction;
    if (!r.finished) {
      status(t('run.progress', { target: TARGETS[tg].label, level: levelName(lv), pct: Math.floor(fraction * 100),
        current: [...r.current].slice(0, 3).join(', ') || '…' }));
      const eta = fraction > 0.02 ? elapsed / fraction - elapsed : null;
      $('detail').textContent = t('run.detail', { done: jobs.filter(j => j.state === 'written' || j.state === 'kept').length,
        total: jobs.length, read: gb(r.read), written: gb(r.written), time: minutes(elapsed) }) +
        (eta ? t('run.eta', { time: minutes(eta) }) : '');
    }
  }, 500);

  try {
    await clearTemp();
    const root = await navigator.storage.getDirectory();
    tmpDir = await root.getDirectoryHandle('t6pack-tmp', { create: true });
    const quota = await navigator.storage.estimate?.();
    if (quota && quota.quota - quota.usage < 4e9) note(t('note.quota', { size: gb(quota.quota - quota.usage) }));

    // Workers: each takes the largest waiting file; no more packed outputs wait than there are workers.
    const count = Math.min(workerCount(), Math.max(1, packQueue.length));
    let waitingOutputs = 0, nextId = 1;
    const dispatch = async worker => {
      while (!r.cancelled && packQueue.length) {
        while (waitingOutputs >= count && !r.cancelled) await new Promise(res => setTimeout(res, 200));
        const job = packQueue.shift();
        if (!job || r.cancelled) return;
        job.state = 'packing';
        r.current.add(job.rel);
        const id = nextId++;
        const reply = await new Promise(resolve => {
          worker.onmessage = ({ data }) => {
            if (data.progress !== undefined) job.progress = data.progress;
            else resolve(data);
          };
          worker.onerror = event => resolve({ error: event.message || t('error.worker') });
          job.getFile().then(file => worker.postMessage({ id, file, args: [...job.args, '--level', ZSTD_LEVEL, '--threads', '1'] }),
            error => resolve({ error: error.message }));
        });
        r.current.delete(job.rel);
        job.progress = 1;
        if (reply.error) {
          // The game still works with the original file: copy it and say so.
          note(t('note.packfail', { file: job.rel, error: reply.error }));
          job.args = null;
          job.sunk = 0;
          pushReady(job, true);
        } else {
          job.output = reply.output;
          job.outSize = reply.result.after;
          job.method = reply.result.method;
          waitingOutputs++;
          pushReady(job, true);
        }
      }
    };
    for (let i = 0; i < count; i++) r.workers.push(new Worker('./worker.js', { type: 'module' }));
    const packers = Promise.all(r.workers.map(dispatch));

    // The sink: one file at a time, in the order they become ready.
    while (toSink > 0) {
      if (r.cancelled) throw new DOMException('Cancelled.', 'AbortError');
      if (!ready.length) await new Promise(res => { wakeSink = res; });
      if (!ready.length) continue;
      const job = ready.shift();
      let written = 0;
      const counter = counting(n => { written += n; job.sunk = written; }, () => r.cancelled);
      if (job.output) {
        const file = await (await tmpDir.getFileHandle(job.output)).getFile();
        await sink.save(job.rel, file.stream().pipeThrough(counter));
        await tmpDir.removeEntry(job.output).catch(() => {});
        waitingOutputs--;
      } else {
        r.current.add(job.rel);
        await sink.save(job.rel, (await job.getFile()).stream().pipeThrough(counter));
        r.current.delete(job.rel);
      }
      job.state = 'written';
      r.read += job.size;
      r.written += written;
      toSink--;
      if (job.key !== 'nro') manifest.files[job.rel] = { key: job.key, out: written };
      if (job.args || job.size > 64e6 || job.key === 'nro')
        note(`${job.rel}: ${(job.size / 1e6).toFixed(1)} → ${(written / 1e6).toFixed(1)} MB (${job.key === 'nro' ? 'BO2 Requiem ' + (release.name || release.tag) : job.method || t('note.copy')})`);
      if (toSink % 25 === 0) await sink.writeManifest(manifest).catch(() => {});
    }
    await packers;
    await sink.writeManifest(manifest);
    await sink.close();
    r.finished = true;
    const seconds = (performance.now() - started) / 1000;
    $('detail').textContent = t('run.detail', { done: jobs.length, total: jobs.length, read: gb(r.read), written: gb(r.written),
      time: minutes(seconds) });
    const where = prefix.join('/') + '/';
    status(t('done', { time: minutes(seconds), read: gb(r.read), written: gb(r.written) }) + (tg === 'switch'
      ? t(toZip ? 'done.switch.zip' : 'done.switch.folder')
      : t(toZip ? 'done.android.zip' : 'done.android.folder', { where })));
    note(t('note.done', { read: gb(r.read), written: gb(r.written), time: minutes(seconds) }));
  } catch (error) {
    failure = error;
    r.finished = true;
    if (error.name === 'AbortError') status(t(toZip ? 'cancelled.zip' : 'cancelled.folder'));
    else status(t('error', { message: error.message || String(error) }));
    await sink.writeManifest(manifest).catch(() => {});
  } finally {
    clearInterval(timer);
    for (const w of r.workers) w.terminate();
    await clearTemp().catch(() => {});
    run = null;
    $('cancel').hidden = true;
    for (const el of [$('source'), $('modes'), $('levels'), $('targets')]) el.disabled = false;
    updateButtons();
    $('progress').value = failure ? $('progress').value : 1;
  }
}

$('source').addEventListener('click', pickSource);
$('install').addEventListener('click', () => install(false));
$('zip').addEventListener('click', () => install(true));
$('cancel').addEventListener('click', () => { if (run) { run.cancelled = true; for (const w of run.workers) w.terminate(); status(t('run.cancelling')); } });
for (const radio of document.querySelectorAll('input[name=level], input[name=target]')) radio.addEventListener('change', updateButtons);
for (const box of document.querySelectorAll('input[name=mode]'))
  box.addEventListener('change', () => {
    if (box.checked) chosen.add(box.value); else chosen.delete(box.value);
    if (entries) showSizes();
    updateButtons();
  });

// ---- the language: asked first, before the setup -----------------------------------------------
const LANGUAGE_KEY = 't6-installer-language';
function savedLanguage() {
  try { return localStorage.getItem(LANGUAGE_KEY); } catch { return null; }
}

// The page's text again in the chosen language, with what the setup already shows.
function chooseLanguage(lang) {
  setLanguage(lang);
  try { localStorage.setItem(LANGUAGE_KEY, language()); } catch {}
  for (const button of document.querySelectorAll('.lang')) button.classList.toggle('current', button.dataset.lang === language());
  showRelease();
  if (entries) { showSourceLabel(); showModes(); showSizes(); }
  updateButtons();
  $('language').hidden = true;
  $('lead').hidden = false;
  $('setup').hidden = false;
  $('footer').hidden = false;
}

for (const button of document.querySelectorAll('.lang')) button.addEventListener('click', () => chooseLanguage(button.dataset.lang));
$('change-language').addEventListener('click', () => {
  if (run) return;
  $('setup').hidden = true;
  $('footer').hidden = true;
  $('language').hidden = false;
  document.querySelector('.lang.current')?.focus();
});
{
  // The last choice is marked and focused, so Enter takes it again.
  const last = savedLanguage();
  const button = last && LANGUAGES[last] && document.querySelector(`.lang[data-lang=${last}]`);
  if (button) { button.classList.add('current'); button.focus(); }
}
updateButtons();
loadRelease();
