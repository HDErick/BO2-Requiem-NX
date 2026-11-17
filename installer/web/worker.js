// One packing job at a time: runs t6pack (WebAssembly) on one game file. The input is read in
// place from the user's File (WORKERFS); outputs go to this origin's private storage (OPFS) through
// synchronous access handles, so the C++ sees ordinary seekable files (src/util.cpp, /opfs/).
// The page streams the finished output to the install folder or the ZIP, then deletes it.
import createT6pack from './generated/t6pack.mjs';

let wasmBinary;
let tmpDir;
const SLOTS = 3;   // the most files one command has open: a bank's plain copy, its container, a spare

async function setup() {
  if (!wasmBinary) {
    const response = await fetch(new URL('./generated/t6pack.wasm', import.meta.url));
    if (!response.ok) throw new Error('generated/t6pack.wasm is missing (build it with build_web.py).');
    wasmBinary = new Uint8Array(await response.arrayBuffer());
  }
  if (!tmpDir) {
    const root = await navigator.storage.getDirectory();
    tmpDir = await root.getDirectoryHandle('t6pack-tmp', { create: true });
  }
}

// Logical /opfs/ paths mapped onto this job's slot files.
function fileTable(handles) {
  const byPath = new Map();   // path -> slot
  const free = () => {
    const used = new Set(byPath.values());
    for (let i = 0; i < handles.length; i++) if (!used.has(i)) return i;
    throw new Error('t6pack opened too many files');
  };
  return {
    byPath,
    open(path, write) {
      let slot = byPath.get(path);
      if (write) {
        if (slot === undefined) slot = free();
        handles[slot].truncate(0);
        byPath.set(path, slot);
      }
      return slot === undefined ? -1 : slot;
    },
    read: (id, view, at) => handles[id].read(view, { at }),
    write: (id, view, at) => handles[id].write(view, { at }),
    size: id => handles[id].getSize(),
    close: id => handles[id].flush(),
    rename(from, to) {
      const slot = byPath.get(from);
      if (slot === undefined) return 0;
      const old = byPath.get(to);
      if (old !== undefined && old !== slot) handles[old].truncate(0);
      byPath.delete(from);
      byPath.set(to, slot);
      return 1;
    },
    remove(path) {
      const slot = byPath.get(path);
      if (slot === undefined) return;
      handles[slot].truncate(0);
      byPath.delete(path);
    },
    stat(path) {
      const slot = byPath.get(path);
      return slot === undefined ? -1 : handles[slot].getSize();
    },
  };
}

self.onmessage = async ({ data }) => {
  const { id, file, args } = data;
  const names = Array.from({ length: SLOTS }, (_, k) => `job-${id}-${k}`);
  const handles = [];
  try {
    await setup();
    for (const name of names) {
      const handle = await tmpDir.getFileHandle(name, { create: true });
      handles.push(await handle.createSyncAccessHandle());
    }
    const errors = [];
    let result = null;
    const module = await createT6pack({
      wasmBinary,
      print: line => {
        if (line.startsWith('P ')) {
          const [, done, total] = line.split(' ');
          self.postMessage({ id, progress: Math.min(1, Number(done) / Math.max(1, Number(total))) });
        } else if (line.startsWith('R ')) {
          result = JSON.parse(line.slice(2));
        }
      },
      printErr: line => errors.push(line),
    });
    const files = fileTable(handles);
    module.t6files = files;
    module.FS.mkdir('/in');
    module.FS.mount(module.WORKERFS, { files: [file] }, '/in');
    const argv = args.map(a => a === '$IN' ? '/in/' + file.name : a === '$OUT' ? '/opfs/out' : a);
    let code;
    try {
      code = module.callMain(argv);
    } catch (error) {
      throw new Error(errors.join(' ') || (error && error.message) || String(error));
    }
    if (code !== 0 || !result) throw new Error(errors.join(' ').replace(/^t6pack: /, '') || `t6pack exit code ${code}`);
    const slot = files.byPath.get('/opfs/out');
    if (slot === undefined) throw new Error('t6pack wrote no output');
    for (const h of handles) h.close();
    handles.length = 0;
    // The other slots are scratch: delete them now, the page deletes the output after copying it.
    for (let k = 0; k < SLOTS; k++) if (k !== slot) await tmpDir.removeEntry(names[k]).catch(() => {});
    self.postMessage({ id, done: true, result, output: names[slot] });
  } catch (error) {
    for (const h of handles) { try { h.close(); } catch {} }
    for (const name of names) await tmpDir?.removeEntry(name).catch(() => {});
    self.postMessage({ id, error: (error && error.message) || String(error) });
  }
};
