// From the OpenBLOPS-NX installer (github.com/HDErick/OpenBLOPS-NX, installer/sw.js).
// Streams "Save as ZIP" to a normal browser download on browsers without
// showSaveFilePicker (Firefox, Safari). The page posts the archive in chunks
// through a MessagePort while it is being made; this worker answers the
// download navigation (./download/<id>/<name>) with a stream of them, so a
// multi-GB package never has to fit in memory. pull() is the backpressure:
// the page sends a chunk only after the download asked for one.
const downloads = new Map();

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));

self.addEventListener('message', event => {
  const data = event.data || {};
  if (data.type !== 'download') return;   // 'ping' only keeps this worker alive
  const port = event.ports[0];
  let controller;
  const stream = new ReadableStream({
    start(c) { controller = c; },
    pull() { port.postMessage({ type: 'pull' }); },
    cancel() { port.postMessage({ type: 'cancel' }); },
  }, { highWaterMark: 4 });
  port.onmessage = ({ data: message }) => {
    if (message.type === 'chunk') controller.enqueue(new Uint8Array(message.chunk));
    else if (message.type === 'close') controller.close();
    else if (message.type === 'error') controller.error(new Error(message.message));
  };
  downloads.set(data.id, { stream, name: data.name });
  port.postMessage({ type: 'ready' });
});

self.addEventListener('fetch', event => {
  const match = new URL(event.request.url).pathname.match(/\/download\/([^/]+)\/[^/]+$/);
  const download = match && downloads.get(match[1]);
  if (!download) return;
  downloads.delete(match[1]);
  event.respondWith(new Response(download.stream, {
    headers: {
      'Content-Type': 'application/zip',
      'Content-Disposition': `attachment; filename="${download.name}"`,
      'X-Content-Type-Options': 'nosniff',
    },
  }));
});
