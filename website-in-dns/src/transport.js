// The loader only accepts the ASCII protocol below. DNS presentation escapes
// are decoded per character-string; separate RRs are never implicitly joined.
function txt(data) {
  if (typeof data !== 'string') throw Error('TXT data is not text');
  if (!data.startsWith('"')) return data; // Google JSON uses bare TXT data.
  let out = '', i = 0;
  while (i < data.length) {
    while (/\s/.test(data[i] || '') && i < data.length) i++;
    if (i === data.length) break;
    if (data[i++] !== '"') throw Error('Invalid TXT string');
    let closed = false;
    while (i < data.length) {
      let c = data[i++];
      if (c === '"') { closed = true; break; }
      if (c === '\\') {
        if (/^\d{3}/.test(data.slice(i))) {
          const n = Number(data.slice(i, i + 3));
          if (n > 255) throw Error('Invalid TXT escape');
          c = String.fromCharCode(n); i += 3;
        } else {
          if (i >= data.length) throw Error('Incomplete TXT escape');
          c = data[i++];
        }
      }
      out += c;
    }
    if (!closed) throw Error('Unclosed TXT string');
  }
  return out;
}
function decode64(s) {
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(s)) throw Error('Invalid base64');
  return Uint8Array.from(atob(s), c => c.charCodeAt(0));
}
async function digest(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
}
function parseManifest(s) {
  if (!s.startsWith('wd1:m:')) throw Error('Missing manifest prefix');
  const bytes = decode64(s.slice(6));
  const m = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(bytes));
  if (m.v !== 1 || m.encoding !== 'gzip+base64' || !/^v[a-f0-9]{20}$/.test(m.release) ||
      !Number.isInteger(m.chunks) || m.chunks < 1 || m.chunks > 1024 ||
      !Number.isInteger(m.bytes) || m.bytes < 1 || m.bytes > 2*1024*1024 ||
      !Number.isInteger(m.decodedBytes) || m.decodedBytes < 1 || m.decodedBytes > 8*1024*1024 ||
      !/^[a-f0-9]{64}$/.test(m.sha256)) throw Error('Unsupported or oversized manifest');
  return {m, bytes};
}
async function mapLimit(items, limit, fn) {
  const out = new Array(items.length); let next = 0, failure;
  await Promise.all(Array.from({length:Math.min(limit, items.length)}, async () => {
    while (next < items.length && !failure) {
      const i = next++;
      try { out[i] = await fn(items[i], i); }
      catch (error) { failure = error; }
    }
  }));
  // Drain in-flight requests before the caller displays its final error or retries.
  if (failure) throw failure;
  return out;
}
async function inflateBounded(bytes, expected) {
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')).getReader();
  const pieces = []; let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > expected) throw Error('Decompressed document exceeds manifest');
      pieces.push(value);
    }
  } finally { await reader.cancel(); }
  if (size !== expected) throw Error('Decompressed length mismatch');
  return new TextDecoder('utf-8', {fatal:true}).decode(await new Blob(pieces).arrayBuffer());
}
