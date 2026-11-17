// From the OpenBLOPS-NX installer (github.com/HDErick/OpenBLOPS-NX, installer/zip-writer.mjs).
// Streaming ZIP64 writer for the installer's "Save as ZIP" output. Entries are
// stored (the zones are already compressed and copying is faster), the CRC is
// computed while streaming and written in a data descriptor, so no entry is
// ever held in memory and archives past 4 GB work.

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[i] = c >>> 0;
  }
  return table;
})();

function crc32(crc, bytes) {
  let c = ~crc >>> 0;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return ~c >>> 0;
}

function dosDateTime(date) {
  const time = (date.getHours() << 11) | (date.getMinutes() << 5) | (date.getSeconds() >> 1);
  const day = ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
  return { time, day };
}

class Bytes {
  constructor(size) { this.buffer = new Uint8Array(size); this.view = new DataView(this.buffer.buffer); this.at = 0; }
  u16(v) { this.view.setUint16(this.at, v, true); this.at += 2; return this; }
  u32(v) { this.view.setUint32(this.at, v >>> 0, true); this.at += 4; return this; }
  u64(v) { this.view.setBigUint64(this.at, BigInt(v), true); this.at += 8; return this; }
  raw(bytes) { this.buffer.set(bytes, this.at); this.at += bytes.length; return this; }
}

const FLAGS = 0x0808;     // sizes and CRC in a data descriptor; UTF-8 names
const VERSION = 45;       // ZIP64

export class ZipWriter {
  constructor(writable) {
    this.writable = writable;
    this.offset = 0;
    this.entries = [];
    this.stamp = dosDateTime(new Date());
  }

  async #write(bytes) {
    await this.writable.write(bytes);
    this.offset += bytes.length;
  }

  // path: "a/b/c.ext"; stream: ReadableStream of Uint8Array.
  async add(path, stream) {
    const name = new TextEncoder().encode(path);
    const local = this.offset;
    const header = new Bytes(30 + name.length + 20)
      .u32(0x04034b50).u16(VERSION).u16(FLAGS).u16(0)
      .u16(this.stamp.time).u16(this.stamp.day)
      .u32(0).u32(0xffffffff).u32(0xffffffff)
      .u16(name.length).u16(20).raw(name)
      .u16(0x0001).u16(16).u64(0).u64(0);
    await this.#write(header.buffer);
    let crc = 0, size = 0;
    const reader = stream.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = value instanceof Uint8Array ? value : new Uint8Array(value);
      crc = crc32(crc, chunk);
      size += chunk.length;
      await this.#write(chunk);
    }
    await this.#write(new Bytes(24).u32(0x08074b50).u32(crc).u64(size).u64(size).buffer);
    this.entries.push({ name, crc, size, local });
  }

  async close() {
    const start = this.offset;
    for (const { name, crc, size, local } of this.entries) {
      await this.#write(new Bytes(46 + name.length + 28)
        .u32(0x02014b50).u16(VERSION).u16(VERSION).u16(FLAGS).u16(0)
        .u16(this.stamp.time).u16(this.stamp.day)
        .u32(crc).u32(0xffffffff).u32(0xffffffff)
        .u16(name.length).u16(28).u16(0).u16(0).u16(0).u32(0).u32(0xffffffff)
        .raw(name)
        .u16(0x0001).u16(24).u64(size).u64(size).u64(local).buffer);
    }
    const end = this.offset;
    const count = this.entries.length;
    await this.#write(new Bytes(56)
      .u32(0x06064b50).u64(44).u16(VERSION).u16(VERSION).u32(0).u32(0)
      .u64(count).u64(count).u64(end - start).u64(start).buffer);
    await this.#write(new Bytes(20).u32(0x07064b50).u32(0).u64(end).u32(1).buffer);
    await this.#write(new Bytes(22)
      .u32(0x06054b50).u16(0).u16(0).u16(0xffff).u16(0xffff)
      .u32(0xffffffff).u32(0xffffffff).u16(0).buffer);
    await this.writable.close();
  }
}
