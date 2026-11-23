// The decoder and the CSV grammar both carry state across byte boundaries.
export async function readCSV(file, onRow, progress) {
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let row = [],
    field = '',
    quoted = false,
    afterQuote = false,
    skipLF = false;
  let record = 1,
    recordSize = 0;

  function finishRow() {
    row.push(field);
    onRow(row, record++);
    row = [];
    field = '';
    recordSize = 0;
  }
  function parse(text) {
    for (const ch of text) {
      if (skipLF) {
        skipLF = false;
        if (ch === '\n') continue;
      }
      if (++recordSize > 4 * 1024 * 1024) throw Error('CSV record exceeds 4 million characters.');
      if (quoted) {
        if (ch === '"') {
          quoted = false;
          afterQuote = true;
        } else field += ch;
      } else if (ch === '"' && afterQuote) {
        field += '"';
        quoted = true;
        afterQuote = false;
      } else if (ch === ',') {
        row.push(field);
        field = '';
        afterQuote = false;
      } else if (ch === '\n' || ch === '\r') {
        finishRow();
        afterQuote = false;
        skipLF = ch === '\r';
      } else if (ch === '"' && !field && !afterQuote) {
        quoted = true;
      } else if (afterQuote || ch === '"') {
        throw Error('Unexpected character near quote in CSV record ' + record);
      } else {
        field += ch;
      }
    }
  }
  const chunk = 256 * 1024;
  for (let offset = 0; offset < file.size; offset += chunk) {
    const bytes = await file.slice(offset, offset + chunk).arrayBuffer();
    parse(decoder.decode(bytes, { stream: true }));
    progress(offset + bytes.byteLength);
  }
  parse(decoder.decode());
  if (quoted) throw Error('Unclosed quote in CSV record ' + record);
  if (row.length || field || afterQuote) finishRow();
  if (record === 1) throw Error('CSV is empty.');
}
